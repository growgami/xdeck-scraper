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
        
    def _get_category_context(self, category):
        """Get specific context and focus areas for each category"""
        contexts = {
            'NEAR Ecosystem': """
            Focus Areas:
            - Protocol Development & Infrastructure
            - DeFi and Smart Contract Innovations
            - Cross-chain Integrations & Bridges
            - Developer Tools & SDKs
            - Ecosystem Growth & Adoption
            - AI & Web3 Integration
            """,
            'Polkadot Ecosystem': """
            Focus Areas:
            - Parachain Development & Integration
            - Cross-chain Messaging (XCM)
            - Governance & Treasury
            - Technical Infrastructure
            - Ecosystem Partnerships
            """,
            'Arbitrum Ecosystem': """
            Focus Areas:
            - Layer 2 Scaling Solutions
            - Protocol Deployments & TVL
            - Governance & DAO Activities
            - Infrastructure Development
            - Ecosystem Growth Initiatives
            """,
            'IOTA Ecosystem': """
            Focus Areas:
            - Protocol Development & Updates
            - Smart Contract Platform
            - IoT Integration & Use Cases
            - Network Security & Performance
            - Industry Partnerships
            """,
            'AI Agents': """
            Focus Areas:
            - Agent Development Frameworks
            - AI-Blockchain Integration
            - Autonomous Systems & DAOs
            - Multi-agent Systems
            - AI Safety & Governance
            - Real-world Applications
            """,
            'DefAI': """
            Focus Areas:
            - Decentralized AI Infrastructure
            - AI Model Training & Deployment
            - Data Privacy & Security
            - Tokenized AI Systems
            - Cross-chain AI Solutions
            """
        }
        return contexts.get(category, "")

    async def analyze_tweets(self, tweets, category):
        """Analyze tweets and categorize them using Deepseek API"""
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
        """Format the summary according to Flow #6 requirements"""
        lines = [f"{date_str} - {category} Rollup\n"]
        
        # Process each subcategory
        for subcategory, tweets in subcategories.items():
            if not tweets or len(tweets) < 3:  # Skip empty subcategories or those with <3 tweets
                continue
                
            lines.append(f"{subcategory} 📌")
            for tweet in tweets:
                lines.append(f"{tweet['author']}: {tweet['summary']} {tweet['url']}")
            lines.append("")  # Empty line between subcategories
            
        # Add Other Updates last if it exists and has tweets
        if "Other Updates" in subcategories and subcategories["Other Updates"]:
            lines.append("Other Updates 📌")
            for tweet in subcategories["Other Updates"]:
                lines.append(f"{tweet['author']}: {tweet['summary']} {tweet['url']}")
        
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
            total_filtered = 0
            
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
                    # Track filtered tweets
                    filtered_count = result.get('filtered_count', 0)
                    total_filtered += filtered_count
                    logger.info(f"Filtered out {filtered_count} tweets from {category}")
                    
                    # Format summary
                    summary = self.format_summary(date_str, category, result['subcategories'])
                    summaries[category] = {
                        'text': summary,
                        'subcategories': result['subcategories'],
                        'filtered_count': filtered_count
                    }
                    
                    # Log subcategory stats
                    for subcat, tweets in result['subcategories'].items():
                        logger.info(f"{category} - {subcat}: {len(tweets)} tweets")
                else:
                    logger.error(f"Failed to generate summary for {category}")
            
            # Save summaries with metadata
            summary_data = {
                'date': date_str,
                'total_filtered': total_filtered,
                'summaries': summaries
            }
            
            summary_file = self.summaries_dir / f'summaries_{date_str}.json'
            with open(summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)
                
            logger.info(f"Saved summaries to {summary_file}. Total filtered tweets: {total_filtered}")
            
        except Exception as e:
            logger.error(f"Error processing news: {str(e)}")
            raise
            
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