import os
import asyncio
import signal
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import logging
from pathlib import Path
from browser_automation import BrowserAutomation
from tweet_scraper import TweetScraper
import json

class TwitterNewsBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Initialize configuration
        self.config = {
            'twitter_username': os.getenv('TWITTER_USERNAME'),
            'twitter_password': os.getenv('TWITTER_PASSWORD'),
            'twitter_2fa': os.getenv('TWITTER_VERIFICATION_CODE'),
            'tweetdeck_url': os.getenv('TWEETDECK_URL'),
            'telegram_token': os.getenv('TELEGRAM_BOT_TOKEN'),
            'telegram_channels': {
                'polkadot': os.getenv('TELEGRAM_POLKADOT_CHANNEL_ID'),
                'iota': os.getenv('TELEGRAM_IOTA_CHANNEL_ID'),
                'arbitrum': os.getenv('TELEGRAM_ARBITRUM_CHANNEL_ID'),
                'near': os.getenv('TELEGRAM_NEAR_CHANNEL_ID'),
                'ai_agents': os.getenv('TELEGRAM_AI_AGENTS_CHANNEL_ID'),
                'crypto_news': os.getenv('TELEGRAM_CRYPTO_NEWS_CHANNEL_ID')
            },
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
            'monitor_interval': float(os.getenv('MONITOR_INTERVAL', '0.1')),  # Default 100ms
            'max_retries': int(os.getenv('MAX_RETRIES', '3')),
            'retry_delay': float(os.getenv('RETRY_DELAY', '2.0'))  # Seconds between retries
        }
        
        # Initialize components
        self.browser = None
        self.scraper = None
        self.is_running = True
        self._shutdown_event = asyncio.Event()
        
        # Track monitoring stats
        self.monitor_stats = {
            'start_time': datetime.now(ZoneInfo("UTC")),
            'total_checks': 0,
            'total_tweets_found': 0,
            'errors': 0
        }
        
        # Track last summary time - use UTC timezone
        utc = ZoneInfo('UTC')
        now = datetime.now(utc)
        self.last_summary_time = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Ensure data directories exist
        self.setup_directories()
        
        # Setup logging after directories are created
        self.setup_logging()
        
    def setup_directories(self):
        """Create necessary directories if they don't exist"""
        directories = ['data/raw', 'data/processed', 'data/session', 'logs']
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
        
    async def initialize_browser(self):
        """Initialize and setup the browser for scraping"""
        logger = logging.getLogger(__name__)
        logger.info("Initializing browser...")
        self.browser = BrowserAutomation(self.config)
        
        # Initialize browser
        if not await self.browser.init_browser():
            raise Exception("Failed to initialize browser")
            
        # Handle login
        if not await self.browser.handle_login():
            raise Exception("Failed to login to Twitter")
            
        # Initialize tweet scraper
        self.scraper = TweetScraper(self.browser.page, self.config)
        if not await self.scraper.identify_columns():
            raise Exception("Failed to identify TweetDeck columns")
            
        # Initial scrape of all tweets
        await self.initial_scrape()
            
        logger.info("Browser initialization complete")
        
    async def initial_scrape(self):
        """Initial scraping of all tweets from all columns"""
        logger = logging.getLogger(__name__)
        logger.info("Starting initial tweet scrape...")
        
        # Load any existing latest tweet IDs
        self.scraper.load_latest_tweets()
        
        # Scrape all columns concurrently
        results = await self.scraper.scrape_all_columns(is_monitoring=False)
        
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
            
        except Exception as e:
            logger.error(f"Error monitoring tweets: {str(e)}")
            
    async def process_data(self):
        """Process and deduplicate tweets"""
        logger = logging.getLogger(__name__)
        try:
            from data_processor import DataProcessor
            processor = DataProcessor()
            processed_count = await processor.process_tweets()
            logger.info(f"Successfully processed {processed_count} tweets")
        except Exception as e:
            logger.error(f"Error processing tweets: {str(e)}")
        
    async def generate_summaries(self):
        """Generate AI summaries for each category"""
        logger = logging.getLogger(__name__)
        logger.info("Generating summaries...")
        # TODO: Implement summary generation
        pass
        
    async def send_telegram_updates(self):
        """Send summaries to Telegram channels"""
        logger = logging.getLogger(__name__)
        logger.info("Sending Telegram updates...")
        # TODO: Implement Telegram sending
        pass

    async def shutdown(self):
        """Gracefully shutdown the application"""
        logger = logging.getLogger(__name__)
        logger.info("Shutting down...")
        self.is_running = False
        self._shutdown_event.set()
        
        # Close browser first
        if self.browser:
            await self.browser.close()
            
        # Cancel all running tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} pending tasks")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            
        logger.info("Shutdown complete")
        
    async def run(self):
        """Main execution loop"""
        logger = logging.getLogger(__name__)
        try:
            await self.initialize_browser()
            
            while self.is_running:
                try:
                    # Check for shutdown using configured interval
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        self.config['monitor_interval']
                    )
                    break
                except asyncio.TimeoutError:
                    try:
                        # Monitor for new tweets
                        self.monitor_stats['total_checks'] += 1
                        results = await self.monitor_tweets()
                        
                        # Update stats if we found tweets
                        if results:
                            total_new = sum(count for _, count in results)
                            if total_new > 0:
                                self.monitor_stats['total_tweets_found'] += total_new
                                
                                # Log monitoring stats every 1000 new tweets
                                if self.monitor_stats['total_tweets_found'] % 1000 == 0:
                                    runtime = datetime.now(ZoneInfo("UTC")) - self.monitor_stats['start_time']
                                    logger.info(
                                        f"Monitoring Stats - Runtime: {runtime}, "
                                        f"Checks: {self.monitor_stats['total_checks']}, "
                                        f"Tweets Found: {self.monitor_stats['total_tweets_found']}, "
                                        f"Errors: {self.monitor_stats['errors']}"
                                    )
                        
                        # Check for midnight summaries
                        current_time = datetime.now(ZoneInfo("UTC"))
                        next_summary_time = self.last_summary_time + timedelta(days=1)
                        
                        if current_time >= next_summary_time:
                            logger.info("Starting daily summary generation")
                            await self.process_data()
                            await self.generate_summaries()
                            await self.send_telegram_updates()
                            self.last_summary_time = current_time.replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )
                    except Exception as e:
                        self.monitor_stats['errors'] += 1
                        logger.error(f"Error in monitoring loop: {str(e)}")
                        # Brief pause on error
                        await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            if self.browser:
                await self.browser.close()
            raise

def handle_interrupt():
    """Handle keyboard interrupt - aggressive shutdown"""
    logger = logging.getLogger(__name__)
    logger.info("Received interrupt signal - performing quick shutdown")
    # Force stop everything
    os._exit(0)

async def main():
    bot = None
    try:
        # Setup signal handlers for both Windows and Unix
        signal.signal(signal.SIGINT, lambda s, f: handle_interrupt())
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, lambda s, f: handle_interrupt())
            
        bot = TwitterNewsBot()
        await bot.run()
    except Exception as e:
        logging.getLogger(__name__).error(f"Application error: {str(e)}")
        os._exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        os._exit(0)  # Force immediate exit 