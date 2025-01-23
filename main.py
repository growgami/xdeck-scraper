from dotenv import load_dotenv
load_dotenv()  # This must come before any environment variable access

import os
import asyncio
import signal
import sys
import json
import logging
from datetime import datetime, timedelta
import zoneinfo
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from browser_automation import BrowserAutomation
from tweet_scraper import TweetScraper
from garbage_collector import GarbageCollector
from error_handler import with_retry, RetryConfig, BrowserError

# Reduce httpx logging
logging.getLogger('httpx').setLevel(logging.WARNING)

class TwitterNewsBot:
    def __init__(self):
        # Add strict validation
        required_env_vars = [
            'TWITTER_USERNAME',
            'TWITTER_PASSWORD',
            'TWEETDECK_URL'
        ]
        
        missing = [var for var in required_env_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        # Configuration remains the same
        self.config = {
            'twitter_username': os.getenv('TWITTER_USERNAME'),
            'twitter_password': os.getenv('TWITTER_PASSWORD'),
            'twitter_2fa': os.getenv('TWITTER_VERIFICATION_CODE'),
            'tweetdeck_url': os.getenv('TWEETDECK_URL'),
            'monitor_interval': float(os.getenv('MONITOR_INTERVAL', '0.1')),
            'max_retries': int(os.getenv('MAX_RETRIES', '3')),
            'retry_delay': float(os.getenv('RETRY_DELAY', '2.0')),
            'garbage_collection': {
                'max_days_to_keep': int(os.getenv('MAX_DAYS_TO_KEEP', '7')),
                'max_file_size_mb': int(os.getenv('MAX_FILE_SIZE_MB', '50')),
                'check_interval': int(os.getenv('GC_CHECK_INTERVAL', '3600'))
            }
        }
        
        # Remove all scheduler references
        self.browser = None
        self.scraper = None
        self.garbage_collector = None
        self.is_running = True
        self._shutdown_event = asyncio.Event()
        
        # Monitoring stats remain
        self.monitor_stats = {
            'start_time': datetime.now(zoneinfo.ZoneInfo("UTC")),
            'total_checks': 0,
            'total_tweets_found': 0,
            'errors': 0
        }
        
        # Keep directory setup and logging
        self.today = datetime.now(zoneinfo.ZoneInfo("UTC")).strftime('%Y%m%d')
        self.setup_directories()
        self.setup_logging()
        
    def setup_directories(self):
        """Create necessary directories if they don't exist"""
        directories = ['data/raw', 'data/session', 'logs']
        for dir_path in directories:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            
    def setup_logging(self):
        """Setup logging configuration"""
        log_file = Path('logs') / f'app_{datetime.now().strftime("%Y%m%d")}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(str(log_file)),
                logging.StreamHandler()
            ]
        )
        
    @with_retry(RetryConfig(max_retries=3, base_delay=2.0))
    async def initialize_browser(self):
        """Initialize and setup the browser for scraping with retry logic"""
        logger = logging.getLogger(__name__)
        logger.info("Initializing browser...")
        
        try:
            # Initialize browser components
            self.browser = BrowserAutomation(self.config)
            
            # Initialize browser
            await self.browser.init_browser()
            
            # Handle login
            await self.browser.handle_login()
            
            # Initialize tweet scraper
            self.scraper = TweetScraper(self.browser.page, self.config)
            if not await self.scraper.identify_columns():
                raise BrowserError("Failed to identify TweetDeck columns")
            
            logger.info("Browser initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"Browser initialization error: {str(e)}")
            if self.browser:
                await self.browser.close()
            raise BrowserError(f"Failed to initialize browser: {str(e)}")
            
    async def initial_scrape(self):
        """Initial scraping of all tweets from all columns"""
        logger = logging.getLogger(__name__)
        logger.info("Starting initial tweet scrape...")
        
        # Load any existing latest tweet IDs
        self.scraper.load_latest_tweets()
        
        # Scrape all columns concurrently
        results = await self.scraper.scrape_all_columns()
        
        # Log results
        total_tweets = sum(count for _, count in results)
        for column_id, count in results:
            column = self.scraper.columns[column_id]
            logger.info(f"Initially saved {count} tweets from column {column['title']}")
            
        logger.info(f"Initial scrape complete. Total tweets saved: {total_tweets}")
        
    async def monitor_tweets(self):
        """Check all columns concurrently for updates"""
        logger = logging.getLogger(__name__)
        try:
            # Scrape all columns concurrently
            results = await self.scraper.scrape_all_columns(is_monitoring=True)
            
            # Log results only if new tweets found
            if results:
                total_new_tweets = sum(count for _, count in results)
                if total_new_tweets > 0:
                    for column_id, count in results:
                        if count > 0:
                            column = self.scraper.columns[column_id]
                            logger.info(f"Found {count} new tweets in column {column['title']}")
                    logger.info(f"Total new tweets found: {total_new_tweets}")
                return results
            return None
            
        except Exception as e:
            logger.error(f"Error monitoring tweets: {str(e)}")
            return None
            
    async def run_clean_loop(self):
        """Simplified main loop focusing only on scraping"""
        logger = logging.getLogger(__name__)
        try:
            # Initialize core components
            await self.initialize_components()
            
            # Initial data collection
            await self.initial_scrape()
            
            # Start continuous monitoring
            while self.is_running:
                try:
                    self.monitor_stats['total_checks'] += 1
                    results = await self.monitor_tweets()
                    
                    if results:
                        total_new = sum(count for _, count in results)
                        self.monitor_stats['total_tweets_found'] += total_new
                        
                    await asyncio.sleep(self.config['monitor_interval'])
                    
                except Exception as e:
                    self.monitor_stats['errors'] += 1
                    logger.error(f"Monitoring error: {str(e)}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            await self.shutdown()
            
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Cleanup and shutdown"""
        logger = logging.getLogger(__name__)
        logger.info("Shutting down...")
        self.is_running = False
        
        # Shutdown scheduler
        if hasattr(self, 'scheduler') and self.scheduler.running:
            self.scheduler.shutdown()
        
        # Close browser if open
        if self.browser:
            await self.browser.close()
            
        # Set shutdown event
        self._shutdown_event.set()
            
        # Cancel all running tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} pending tasks")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            
        logger.info("Shutdown complete")
        
    async def initialize_components(self):
        """Initialize only required components"""
        logger = logging.getLogger(__name__)
        
        # Browser and scraper
        await self.initialize_browser()
        
        # Garbage collector
        self.garbage_collector = GarbageCollector(self.config['garbage_collection'])
        asyncio.create_task(self.garbage_collector.start())

def handle_interrupt(signum=None, frame=None):
    """Handle keyboard interrupt - aggressive shutdown"""
    logger = logging.getLogger(__name__)
    logger.info("Received interrupt signal - performing quick shutdown")
    # Force stop everything
    os._exit(0)

async def main():
    """Main entry point for the application"""
    logger = logging.getLogger(__name__)
    bot = None
    
    try:
        # Setup signal handlers for both Windows and Unix
        signal.signal(signal.SIGINT, handle_interrupt)
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, handle_interrupt)
            
        bot = TwitterNewsBot()
        await bot.run_clean_loop()
        
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        if bot:
            await bot.shutdown()
        os._exit(1)
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        os._exit(0)  # Force immediate exit 