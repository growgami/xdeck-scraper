import logging
import json
from pathlib import Path
import re
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self):
        self.data_dir = Path('data')
        self.raw_dir = self.data_dir / 'raw'
        self.processed_dir = self.data_dir / 'processed'
        
        # Get today's date for file naming
        self.today = datetime.now().strftime('%Y%m%d')
        self.today_dir = self.raw_dir / self.today
        
        # Ensure directories exist
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.today_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging when running independently
        if __name__ == '__main__':
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
    def load_column_tweets(self, column_file):
        """Load tweets from a column file"""
        try:
            with open(column_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading tweets from {column_file}: {str(e)}")
            return []
            
    def normalize_text(self, text):
        """Normalize special characters and symbols from text"""
        if not text:
            return text
            
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        
        # Remove non-printable characters
        text = ''.join(char for char in text if char.isprintable())
        
        # Normalize unicode characters
        text = text.replace('"', '"').replace('"', '"')  # Smart quotes
        text = text.replace(''', "'").replace(''', "'")  # Smart apostrophes
        text = text.replace('…', '...')  # Ellipsis
        text = text.replace('–', '-')    # En dash
        text = text.replace('—', '-')    # Em dash
        
        # Remove URLs (optional, but they often contain special chars)
        text = re.sub(r'http[s]?://\S+', '', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text
        
    def is_valid_tweet(self, tweet):
        """Check if a tweet is valid according to our criteria"""
        # Must have text
        if not tweet.get('text'):
            return False
            
        # Text must be at least 2 words (after normalization)
        normalized_text = self.normalize_text(tweet['text'])
        words = [w for w in normalized_text.split() if w.strip()]  # Remove empty strings
        if len(words) < 2:
            return False
            
        return True
        
    async def process_tweets(self, date=None):
        """Process all tweets according to requirements"""
        # Use provided date or today
        process_date = date or self.today
        date_dir = self.raw_dir / process_date
        
        if not date_dir.exists():
            logger.error(f"No data directory found for date {process_date}")
            return 0
            
        logger.info(f"Starting tweet processing for {process_date}")
        
        try:
            # Dictionary to track unique tweets by ID and organize by column
            unique_tweets = {}  # For deduplication
            columns = {}       # Final structure by column
            
            # Process each column's tweets from the date directory
            for column_file in date_dir.glob('column_*.json'):
                tweets = self.load_column_tweets(column_file)
                logger.info(f"Processing {len(tweets)} tweets from {column_file.name}")
                
                for tweet in tweets:
                    # Skip invalid tweets
                    if not self.is_valid_tweet(tweet):
                        continue
                        
                    # Normalize text
                    tweet['text'] = self.normalize_text(tweet['text'])
                    if tweet.get('quotedContent'):
                        tweet['quotedContent']['text'] = self.normalize_text(tweet['quotedContent']['text'])
                    if tweet.get('repostedContent'):
                        tweet['repostedContent']['text'] = self.normalize_text(tweet['repostedContent']['text'])
                    
                    # Store only the most recent version of each tweet
                    tweet_id = tweet['id']
                    if tweet_id not in unique_tweets:
                        unique_tweets[tweet_id] = tweet
                        
                        # Add to column structure
                        column_name = tweet['column']
                        if column_name not in columns:
                            columns[column_name] = []
                        columns[column_name].append(tweet)
            
            # Sort tweets in each column by ID (newer first)
            for column_name in columns:
                columns[column_name].sort(key=lambda x: x['id'], reverse=True)
                logger.info(f"Processed {len(columns[column_name])} unique tweets for column {column_name}")
            
            # Save processed tweets with date in filename
            output_file = self.processed_dir / f'processed_tweets_{process_date}.json'
            total_tweets = len(unique_tweets)
            
            with open(output_file, 'w') as f:
                json.dump({
                    'date': process_date,
                    'total_tweets': total_tweets,
                    'columns': columns
                }, f, indent=2)
            logger.info(f"Saved {total_tweets} processed tweets across {len(columns)} columns to {output_file}")
            
            return total_tweets
            
        except Exception as e:
            logger.error(f"Error processing tweets: {str(e)}")
            return 0
            
        finally:
            # Clean up dictionaries
            if 'unique_tweets' in locals():
                unique_tweets.clear()
                del unique_tweets
            if 'columns' in locals():
                columns.clear()
                del columns
            logger.debug("Cleaned up processing dictionaries")

if __name__ == "__main__":
    # Setup and run processor
    processor = DataProcessor()
    
    # Allow processing specific date from command line
    import sys
    date_to_process = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Run the async process_tweets function
    asyncio.run(processor.process_tweets(date_to_process)) 