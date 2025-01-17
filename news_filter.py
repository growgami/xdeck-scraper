"""News filtering and categorization service"""

import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
import zoneinfo
import asyncio
from openai import OpenAI, AsyncOpenAI
from error_handler import with_retry, APIError, log_error, RetryConfig
from category_mapping import CATEGORY_MAP, CATEGORY_FOCUS, EMOJI_MAP

logger = logging.getLogger(__name__)

# Reduce httpx logging
logging.getLogger('httpx').setLevel(logging.WARNING)

class NewsFilter:
    def __init__(self, config):
        self.config = config
        self.data_dir = Path('data')
        self.processed_dir = self.data_dir / 'processed'
        self.summaries_dir = self.data_dir / 'summaries'
        self.api_key = config['deepseek_api_key']
        self.client = AsyncOpenAI(api_key=self.api_key, base_url="https://api.deepseek.com/v1")
        self.retry_config = RetryConfig(max_retries=3, base_delay=2.0, max_delay=30.0)
        
        # Ensure directories exist
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        
        # Use centralized category mapping
        self.categories = CATEGORY_MAP

    def _get_category_context(self, category):
        """Get specific context and focus areas for each category"""
        return "\n".join([
            "Focus Areas:",
            *[f"- {focus}" for focus in CATEGORY_FOCUS.get(category, [])]
        ])

    @with_retry(RetryConfig(max_retries=3, base_delay=2.0))
    async def analyze_tweets(self, tweets, category):
        """Analyze tweets using DeepSeek API with retry logic"""
        try:
            prompt = f"""
            You are a specialized crypto and web3 analyst focusing on {category}. Your task is to filter and categorize tweets for the daily news summary.

            ### Filtering Rules
            First, filter out tweets that:
            1. Lack direct relevance to {category}'s ecosystem
            2. Contain no concrete, verifiable information
            3. Have no clear ecosystem impact
            4. Are generic announcements without specifics
            5. Are retweets without additional valuable context
            6. Are promotional without significant news value

            ### Categorization Rules
            After filtering, organize remaining tweets into subcategories:
            1. Maximum 5 subcategories (excluding "Other Updates")
            2. Each subcategory must have at least 3 tweets
            3. If a subcategory has fewer than 3 tweets, move them to "Other Updates"
            4. Choose subcategory names that reflect major themes or developments
            5. Ensure subcategories are specific to {category}

            ### Category Context
            {self._get_category_context(category)}

            ### Summary Creation Rules
            For each tweet:
            - Create extremely concise summaries (max 12 words)
            - Focus on concrete facts and metrics
            - Use technical, precise language
            - Include quantifiable metrics when available
            - Format: "[Key Action/Development] with [Specific Detail]"

            Tweets to analyze:
            {json.dumps(tweets, indent=2)}

            ### Response Format
            You must return your response in the following JSON format:
            {{
                "filtered_count": 123,  // Number of tweets filtered out
                "subcategories": {{     // Maximum 5 subcategories + "Other Updates"
                    "Technical Name": [  // Each subcategory must have >= 3 tweets
                        {{
                            "author": "handle",
                            "summary": "precise technical summary",
                            "url": "tweet_url"
                        }}
                    ],
                    "Other Updates": [   // For tweets that don't fit main subcategories or groups with <3 tweets
                        {{
                            "author": "handle",
                            "summary": "precise technical summary",
                            "url": "tweet_url"
                        }}
                    ]
                }}
            }}

            Remember:
            - Apply filtering rules strictly
            - Ensure each subcategory has at least 3 tweets
            - Move tweets from subcategories with <3 tweets to "Other Updates"
            - Use professional, technical subcategory names
            - Maintain consistency in technical terminology
            """
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=4096
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
                        
        except Exception as e:
            log_error(logger, e, "Failed to analyze tweets")
            raise APIError(f"Tweet analysis failed: {str(e)}")
            
    def _get_emoji(self, subcategory):
        """Get appropriate emoji for a subcategory"""
        # Find best matching key
        for key in EMOJI_MAP:
            if key.lower() in subcategory.lower():
                return EMOJI_MAP[key]
        return EMOJI_MAP['Other Updates']  # Default emoji if no match

    def format_summary(self, date_str, category, subcategories):
        """Format the summary according to Flow #6 requirements"""
        lines = [f"{date_str} - {category} Rollup\n"]
        
        # First process main subcategories (excluding "Other Updates")
        main_subcategories = {k: v for k, v in subcategories.items() if k != "Other Updates"}
        for subcategory, tweets in main_subcategories.items():
            if tweets:  # Add subcategory even if less than 3 tweets
                lines.append(f"{subcategory} {self._get_emoji(subcategory)}")
                for tweet in tweets:
                    lines.append(f"{tweet['author']}: {tweet['summary']}")
                    lines.append(f"{tweet['url']}")
                lines.append("")  # Empty line between subcategories
            
        # Then add Other Updates last if it exists
        if "Other Updates" in subcategories and subcategories["Other Updates"]:
            lines.append(f"Other Updates {self._get_emoji('Other Updates')}")
            for tweet in subcategories["Other Updates"]:
                lines.append(f"{tweet['author']}: {tweet['summary']}")
                lines.append(f"{tweet['url']}")
                
        return "\n".join(lines)
        
    @with_retry(RetryConfig(max_retries=2, base_delay=1.0))
    async def process_news(self, date_str=None):
        """Process and filter news with retry logic"""
        try:
            if not date_str:
                # Default to yesterday's date
                current_time = datetime.now(zoneinfo.ZoneInfo("UTC"))
                yesterday = current_time - timedelta(days=1)
                date_str = yesterday.strftime('%Y%m%d')
                
            logger.info(f"Processing news for date: {date_str}")
            
            # Load processed tweets
            file_path = self.processed_dir / f'processed_tweets_{date_str}.json'
            if not file_path.exists():
                logger.error(f"No processed tweets file found for date {date_str}")
                return
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            summaries = {}
            total_filtered = 0
            
            # Process each column
            for column_id, tweets in data['columns'].items():
                try:
                    if not tweets:
                        logger.info(f"Skipping empty column {column_id}")
                        continue
                        
                    category = self.categories.get(column_id)
                    if not category:
                        logger.warning(f"No category mapping found for column {column_id}")
                        continue
                        
                    logger.info(f"Analyzing {len(tweets)} tweets for {category}")
                    
                    # Analyze and categorize tweets
                    result = await self.analyze_tweets(tweets, category)
                    if result and 'subcategories' in result:
                        filtered_count = result.get('filtered_count', 0)
                        total_filtered += filtered_count
                        
                        # Format summary
                        summary = self.format_summary(date_str, category, result['subcategories'])
                        summaries[category] = {
                            'text': summary,
                            'subcategories': result['subcategories'],
                            'filtered_count': filtered_count
                        }
                        
                    else:
                        logger.error(f"Failed to generate summary for {category}")
                        
                except Exception as e:
                    log_error(logger, e, f"Error processing column {column_id}")
                    continue
                    
            # Save summaries
            await self._save_summaries(date_str, summaries, total_filtered)
            
        except Exception as e:
            log_error(logger, e, f"Failed to process news for date {date_str}")
            raise APIError(f"News processing failed: {str(e)}")
            
    async def _save_summaries(self, date_str, summaries, total_filtered):
        """Save summaries with error handling"""
        try:
            summary_data = {
                'date': date_str,
                'total_filtered': total_filtered,
                'summaries': summaries
            }
            
            summary_file = self.summaries_dir / f'summaries_{date_str}.json'
            with open(summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)
                
            logger.info(f"Saved summaries to {summary_file}")
            
        except Exception as e:
            log_error(logger, e, f"Failed to save summaries for date {date_str}")
            raise APIError(f"Failed to save summaries: {str(e)}")
            
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get date to process - either from args or use today's date
    import sys
    date_to_process = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y%m%d')
    
    logger.info(f"Processing news for date: {date_to_process}")
    
    # Load config and run news filter
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'deepseek_api_key': os.getenv('DEEPSEEK_API_KEY')
    }
    
    news_filter = NewsFilter(config)
    asyncio.run(news_filter.process_news(date_to_process)) 