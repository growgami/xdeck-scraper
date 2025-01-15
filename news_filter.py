import logging
import json
from pathlib import Path
from datetime import datetime
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class NewsFilter:
    def __init__(self, config):
        self.config = config
        self.data_dir = Path('data')
        self.processed_dir = self.data_dir / 'processed'
        self.summaries_dir = self.data_dir / 'summaries'
        self.api_key = config['deepseek_api_key']
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        
        # Ensure summaries directory exists
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        
        # Category mappings
        self.categories = {
            '0': 'NEAR Ecosystem',
            '1': 'Polkadot Ecosystem',
            '2': 'Arbitrum Ecosystem',
            '3': 'IOTA Ecosystem',
            '4': 'AI Agents',
            '5': 'DefAI'
        }
        
    async def analyze_tweets(self, tweets, category):
        """Analyze tweets and categorize them using Deepseek API"""
        try:
            prompt = f"""
            You are a crypto and web3 analyst. Your task is to analyze, filter, and categorize tweets for the {category} category.
            
            ### **Strict Filtering Rules**
            You must filter out tweets that match ANY of these criteria:

            1. Relevance:
               - Not directly related to {category} development, technology, or ecosystem
               - Generic crypto market commentary without specific {category} impact
               - Retweets/quotes without additional valuable context
               - Personal opinions without factual basis

            2. Content Quality:
               - No concrete information or verifiable facts
               - Vague announcements without specifics
               - Simple price commentary or price predictions
               - "GM", "GN", or other greeting-only tweets
               - Memes or jokes without substantial information

            3. Promotional Content:
               - Token shilling or "buy now" messages
               - Self-promotional content without news value
               - Marketing language without concrete updates
               - Airdrops or giveaway announcements
               - Trading signals or financial advice

            4. Credibility:
               - Unverified claims without sources
               - Potential scams or suspicious projects
               - Known fake accounts or impersonators
               - Excessive hype or unrealistic claims
               - Outdated or superseded information

            5. Duplicates:
               - Exact or near-duplicate content
               - Multiple tweets about same topic without new info
               - Repeated announcements or reminders
               - Chain posts or thread summaries

            ### **Instructions**
            1. Apply filtering rules STRICTLY - when in doubt, filter out
            2. Analyze remaining high-quality tweets to identify main themes
            3. Determine up to 5 most relevant subcategories that best group these tweets
            4. Each subcategory must have at least 3 tweets, otherwise add those tweets to "Other Updates"
            5. Choose subcategory names that are specific and relevant to {category}
            6. For each tweet, create an extremely concise summary (max 10-15 words)

            ### **Summary Rules**
            - Focus on key facts and actions only
            - Remove unnecessary words and context
            - Use active voice and present tense
            - Include only the most impactful metrics/numbers
            - Format: "author: [concise action/update] [URL]"

            Tweets to analyze:
            {json.dumps(tweets, indent=2)}

            Return the result in the following JSON format:
            {{
                "filtered_count": 123,  // Number of tweets filtered out
                "filter_reasons": {{     // Count of tweets filtered by each main reason
                    "relevance": 45,
                    "quality": 32,
                    "promotional": 21,
                    "credibility": 15,
                    "duplicates": 10
                }},
                "subcategories": {{
                    "Subcategory Name 1": [
                        {{"author": "handle", "summary": "concise action/update", "url": "tweet_url"}}
                    ],
                    "Other Updates": [...]  // For tweets that don't fit main subcategories or groups with <3 tweets
                }}
            }}

            Remember:
            - Be extremely strict with filtering - only keep highest quality tweets
            - Maximum 5 subcategories (excluding "Other Updates")
            - Each subcategory must have at least 3 tweets
            - Subcategory names should be specific to {category}
            - If a potential subcategory has fewer than 3 tweets, move them to "Other Updates"
            """
            
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "max_tokens": 2000
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = json.loads(data['choices'][0]['message']['content'])
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"API error: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error analyzing tweets: {str(e)}")
            return None
            
    def format_summary(self, date_str, category, subcategories):
        """Format the summary according to the required template"""
        lines = [f"{date_str} - {category} Rollup\n"]
        
        for subcategory, tweets in subcategories.items():
            # Skip empty subcategories
            if not tweets:
                continue
                
            lines.append(f"{subcategory} 📌")
            
            for tweet in tweets:
                lines.append(f"{tweet['author']}: {tweet['summary']} {tweet['url']}")
            lines.append("")  # Empty line between subcategories
            
        return "\n".join(lines)
        
    async def process_news(self, date_str=None):
        """Process and filter news for a given date"""
        try:
            # Use today's date if none provided
            if not date_str:
                date_str = datetime.now().strftime('%Y%m%d')
                
            logger.info(f"Processing news for date: {date_str}")
            
            # Load processed tweets
            file_path = self.processed_dir / f'processed_tweets_{date_str}.json'
            if not file_path.exists():
                logger.error(f"No processed tweets file found for date {date_str}")
                return
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            summaries = {}
            
            # Process each column
            for column_id, tweets in data['columns'].items():
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
                    # Format summary
                    summary = self.format_summary(date_str, category, result['subcategories'])
                    summaries[category] = {
                        'text': summary,
                        'subcategories': result['subcategories']
                    }
                    logger.info(f"Generated summary for {category}")
                else:
                    logger.error(f"Failed to generate summary for {category}")
            
            # Save summaries
            summary_file = self.summaries_dir / f'summaries_{date_str}.json'
            with open(summary_file, 'w') as f:
                json.dump(summaries, f, indent=2)
                
            logger.info(f"Saved summaries to {summary_file}")
            
        except Exception as e:
            logger.error(f"Error processing news: {str(e)}")
            
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