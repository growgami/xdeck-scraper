import os
import asyncio
import signal
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import logging
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from browser_automation import BrowserAutomation
from tweet_scraper import TweetScraper
from garbage_collector import GarbageCollector
from error_handler import with_retry, RetryConfig, BrowserError, DataProcessingError, TelegramError
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
                'ai_agent': os.getenv('TELEGRAM_AI_AGENT_CHANNEL_ID'),
                'defi': os.getenv('TELEGRAM_DEFI_CHANNEL_ID'),
                'test': os.getenv('TELEGRAM_TEST_CHANNEL_ID')
            },
            'deepseek_api_key': os.getenv('DEEPSEEK_API_KEY'),
            'monitor_interval': float(os.getenv('MONITOR_INTERVAL', '0.1')),  # Default 100ms
            'max_retries': int(os.getenv('MAX_RETRIES', '3')),
            'retry_delay': float(os.getenv('RETRY_DELAY', '2.0')),  # Seconds between retries
            'garbage_collection': {
                'max_days_to_keep': int(os.getenv('MAX_DAYS_TO_KEEP', '7')),
                'max_file_size_mb': int(os.getenv('MAX_FILE_SIZE_MB', '50')),
                'check_interval': int(os.getenv('GC_CHECK_INTERVAL', '3600'))
            }
        }
        
        # Initialize components
        self.browser = None
        self.scraper = None
        self.garbage_collector = None
        self.is_running = True
        self.is_scraping = True
        self._shutdown_event = asyncio.Event()
        self._processing_lock = asyncio.Lock()
        
        # Track monitoring stats
        self.monitor_stats = {
            'start_time': datetime.now(ZoneInfo("UTC")),
            'total_checks': 0,
            'total_tweets_found': 0,
            'errors': 0
        }
        
        # Initialize scheduler
        self.scheduler = AsyncIOScheduler()
        
        # Get today's date for file organization
        self.today = datetime.now(ZoneInfo("UTC")).strftime('%Y%m%d')
        
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
        
    @with_retry(RetryConfig(max_retries=3, base_delay=2.0))
    async def initialize_browser(self):
        """Initialize and setup the browser for scraping with retry logic"""
        logger = logging.getLogger(__name__)
        logger.info("Initializing browser...")
        
        try:
            self.browser = BrowserAutomation(self.config)
            
            # Initialize browser
            if not await self.browser.init_browser():
                raise BrowserError("Failed to initialize browser")
                
            # Handle login
            if not await self.browser.handle_login():
                raise BrowserError("Failed to login to Twitter")
                
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
            return None
            
        except Exception as e:
            logger.error(f"Error monitoring tweets: {str(e)}")
            return None
        
    async def process_data(self):
        """Process and deduplicate tweets"""
        logger = logging.getLogger(__name__)
        try:
            from data_processor import DataProcessor
            processor = DataProcessor()
            processed_count = await processor.process_tweets(self.today)
            logger.info(f"Successfully processed {processed_count} tweets")
            return processed_count
        except Exception as e:
            logger.error(f"Error processing tweets: {str(e)}")
            raise DataProcessingError(f"Failed to process tweets: {str(e)}")

    async def score_tweets(self):
        """Score tweets using TweetScorer"""
        logger = logging.getLogger(__name__)
        try:
            from tweet_scorer import TweetScorer
            scorer = TweetScorer(self.config)
            await scorer.process_tweets(self.today)
            logger.info("Successfully scored tweets")
            return True
        except Exception as e:
            logger.error(f"Error scoring tweets: {str(e)}")
            raise DataProcessingError(f"Failed to score tweets: {str(e)}")

    async def refine_tweets(self):
        """Refine and deduplicate tweets"""
        logger = logging.getLogger(__name__)
        try:
            from tweet_refiner import TweetRefiner
            refiner = TweetRefiner(self.config)
            await refiner.process_tweets(self.today)
            logger.info("Successfully refined tweets")
            return True
        except Exception as e:
            logger.error(f"Error refining tweets: {str(e)}")
            raise DataProcessingError(f"Failed to refine tweets: {str(e)}")

    async def filter_news(self):
        """Filter and categorize news"""
        logger = logging.getLogger(__name__)
        try:
            from news_filter import NewsFilter
            news_filter = NewsFilter(self.config)
            await news_filter.process_news(self.today)
            logger.info("Successfully filtered and categorized news")
            return True
        except Exception as e:
            logger.error(f"Error filtering news: {str(e)}")
            raise DataProcessingError(f"Failed to filter news: {str(e)}")
        
    async def send_telegram_updates(self):
        """Send summaries to Telegram channels"""
        logger = logging.getLogger(__name__)
        try:
            from telegram_sender import TelegramSender
            sender = TelegramSender(self.config['telegram_token'])
            
            # Load summaries
            summaries_file = Path('data') / 'summaries' / f'summaries_{self.today}.json'
            if not summaries_file.exists():
                logger.error(f"No summaries file found for date {self.today}")
                return False
                
            with open(summaries_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not data or not data.get('summaries'):
                logger.info("No summaries found in file, skipping send")
                return False
                
            # Send to appropriate channels
            for category, content in data['summaries'].items():
                try:
                    if not content.get('text'):
                        logger.info(f"No text content for {category}, skipping")
                        continue
                        
                    # Get channel ID based on category
                    channel_key = category.lower().split()[0]  # e.g., "NEAR Ecosystem" -> "near"
                    channel_id = self.config['telegram_channels'].get(channel_key)
                    if not channel_id:
                        logger.warning(f"No channel ID found for category {category}")
                        continue
                        
                    # Format and send
                    formatted_text = sender.format_text(content['text'])
                    if not formatted_text:
                        logger.info(f"Empty formatted text for {category}, skipping")
                        continue
                        
                    success = await sender.send_message(
                        channel_id=channel_id,
                        text=formatted_text
                    )
                    
                    if success:
                        logger.info(f"Successfully sent {category} summary to channel {channel_id}")
                    else:
                        logger.error(f"Failed to send {category} summary to channel {channel_id}")
                        
                    await asyncio.sleep(2)  # Delay between messages
                    
                except Exception as e:
                    logger.error(f"Error sending {category} summary: {str(e)}")
                    continue
                    
            logger.info("Completed sending all summaries")
            return True
            
        except Exception as e:
            logger.error(f"Error in telegram updates: {str(e)}")
            raise TelegramError(f"Failed to send telegram updates: {str(e)}")

    async def process_daily_summaries(self):
        """Process and generate daily summaries"""
        logger = logging.getLogger(__name__)
        try:
            async with self._processing_lock:
                # Pause continuous scraping
                self.is_scraping = False
                logger.info("Paused continuous scraping for daily processing")
                
                try:
                    # Run the complete pipeline
                    logger.info("Starting daily processing pipeline")
                    
                    # 1. Process raw tweets
                    await self.process_data()
                    logger.info("Completed tweet processing")
                    
                    # 2. Score tweets
                    await self.score_tweets()
                    logger.info("Completed tweet scoring")
                    
                    # 3. Refine and deduplicate
                    await self.refine_tweets()
                    logger.info("Completed tweet refinement")
                    
                    # 4. Filter and categorize
                    await self.filter_news()
                    logger.info("Completed news filtering")
                    
                    # 5. Send to Telegram
                    await self.send_telegram_updates()
                    logger.info("Completed sending updates")
                    
                finally:
                    # Resume continuous scraping
                    self.is_scraping = True
                    logger.info("Resumed continuous scraping")
                    
        except Exception as e:
            logger.error(f"Error in daily summary processing: {str(e)}")
            raise DataProcessingError(f"Failed to process daily summaries: {str(e)}")

    async def continuous_scraping(self):
        """Continuously monitor for new tweets"""
        logger = logging.getLogger(__name__)
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self.is_running:
            try:
                if not self.is_scraping:
                    await asyncio.sleep(1)
                    continue
                    
                # Monitor for new tweets
                self.monitor_stats['total_checks'] += 1
                results = await self.monitor_tweets()
                
                if results:
                    total_new_tweets = sum(count for _, count in results)
                    self.monitor_stats['total_tweets_found'] += total_new_tweets
                    
                # Reset error counter on success
                consecutive_errors = 0
                
                # Brief pause between checks
                await asyncio.sleep(self.config['monitor_interval'])
                
            except Exception as e:
                self.monitor_stats['errors'] += 1
                consecutive_errors += 1
                logger.error(f"Error in scraping loop: {str(e)}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical("Too many consecutive errors, attempting browser reinitialization")
                    try:
                        await self.initialize_browser()
                        consecutive_errors = 0
                    except Exception as reinit_error:
                        logger.error(f"Failed to reinitialize browser: {str(reinit_error)}")
                        
                # Exponential backoff on error
                await asyncio.sleep(min(60, 2 ** consecutive_errors))  # Max 60 seconds

    async def handle_summaries(self):
        """Handle 6 AM UTC summary generation"""
        logger = logging.getLogger(__name__)
        while self.is_running:
            try:
                # Get current time and next summary time
                current_time = datetime.now(ZoneInfo("UTC"))
                next_summary_time = self.last_summary_time
                
                # Calculate seconds until next summary
                seconds_until_summary = (next_summary_time - current_time).total_seconds()
                
                if seconds_until_summary <= 0:
                    # Time for summary
                    logger.info("Starting daily summary generation")
                    await self.process_daily_summaries()
                    
                    # Update last summary time to next 6 AM UTC
                    self.last_summary_time = current_time.replace(
                        hour=6, minute=0, second=0, microsecond=0
                    ) + timedelta(days=1)
                    
                    # Update today's date
                    self.today = current_time.strftime('%Y%m%d')
                    
                # Wait until next summary time (check every minute)
                await asyncio.sleep(min(60, max(0, seconds_until_summary)))
                
            except Exception as e:
                logger.error(f"Error in summary loop: {str(e)}")
                await asyncio.sleep(60)  # Wait a minute before retrying

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
        """Initialize all components"""
        logger = logging.getLogger(__name__)
        
        # Initialize browser and scraper
        await self.initialize_browser()
        
        # Initialize garbage collector
        logger.info("Initializing garbage collector...")
        self.garbage_collector = GarbageCollector(self.config['garbage_collection'])
        
        # Start garbage collection service
        asyncio.create_task(self.garbage_collector.start())
        logger.info("Garbage collector initialized and started")
        
    async def run(self):
        """Main application loop"""
        logger = logging.getLogger(__name__)
        try:
            # Initialize all components
            await self.initialize_components()
            
            # Initial scrape of all columns
            await self.initial_scrape()
            
            # Schedule daily summary generation at 6 AM UTC
            self.scheduler.add_job(
                self.process_daily_summaries,
                CronTrigger(hour=6, minute=0, timezone='UTC'),
                id='daily_summaries',
                replace_existing=True
            )
            
            # Start the scheduler
            self.scheduler.start()
            
            # Start continuous scraping
            await self.continuous_scraping()
            
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            await self.shutdown()
            
        finally:
            await self.shutdown()

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