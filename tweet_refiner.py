import logging
import json
from pathlib import Path
from datetime import datetime
import asyncio
import aiohttp
import re

logger = logging.getLogger(__name__)

class TweetRefiner:
    def __init__(self, config):
        self.config = config
        self.data_dir = Path('data')
        self.processed_dir = self.data_dir / 'processed'
        self.api_key = config['deepseek_api_key']
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.chunk_size = 10  # Process 10 tweets at a time
        
    async def analyze_similarity(self, tweets):
        """Analyze tweet similarity using Deepseek API"""
        try:
            prompt = f"""
            Analyze these tweets for similarity and make a strict determination about deduplication.
            You must identify if tweets are duplicates or share the same core information.

            STRICT RULES FOR DUPLICATES:
            1. Tweets are duplicates if they:
               - Share the same core announcement/news/information (e.g. same partnership announcement)
               - Report identical metrics/numbers (e.g. "7,500 ETH")
               - One tweet quotes or reposts another with minimal new info
               - Cover the same event/update with different wording
               - Share same links or reference same content
               - Mention same project names in similar context (e.g. "Phala x xNomad" and "xNomad x Phala")

            2. When choosing which tweet to keep:
               - Prefer original announcements over quotes/reposts
               - Prefer tweets with more detailed context/information
               - If both tweets add unique perspectives (e.g. both partners announcing collab), keep both
               - If metrics/numbers match exactly, likely duplicates
               - Prefer tweets from official/verified sources
               - For partnership announcements, keep both partners' announcements if they add unique value

            3. Examples of duplicates:
               - Original: "Arbitrum DAO deploys 7,500 ETH"
                 Quote: "Great to see Arbitrum growing! They just deployed 7.5k ETH"
               - Original: "New AI SDK 4.0 released with chat features"
                 Repost: "Check out the new AI SDK 4.0 with chat!"
               - Original: "Project A partners with Project B for X"
                 Partner: "We're excited to work with Project A on X"
                 (Keep both if they provide different perspectives)

            Tweets to analyze:
            {json.dumps(tweets, indent=2)}

            You must return your response in the following JSON format:
            {{
                "are_duplicates": true/false,
                "keep_tweet_ids": ["id1", "id2"],  // IDs of tweets to keep (usually just one unless both add unique value)
                "reason": "Detailed explanation of why tweets are duplicates and which were chosen",
                "confidence": 0.95  // How confident are you in this decision (0.0 to 1.0)
            }}

            If confidence is below 0.95, consider tweets as unique.
            In the reason, specifically mention:
            1. Matching metrics/numbers
            2. Project names and partnerships
            3. Why certain tweets were chosen over others
            4. If both tweets add unique value (e.g. different partner perspectives)
            """

            # API call with retry logic
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            self.api_url,
                            json={
                                "model": "deepseek-chat",
                                "messages": [{
                                    "role": "user",
                                    "content": prompt
                                }],
                                "temperature": 0.1,
                                "response_format": {"type": "json_object"},
                                "max_tokens": 1000
                            },
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"
                            },
                            timeout=30
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                result = json.loads(data['choices'][0]['message']['content'])
                                
                                # Process API response
                                if result.get('confidence', 0) < 0.95:
                                    return {
                                        'action': 'keep_all',
                                        'selected_tweets': [t['id'] for t in tweets],
                                        'reason': 'Confidence too low to determine similarity'
                                    }
                                
                                if result.get('are_duplicates', False):
                                    return {
                                        'action': 'select',
                                        'selected_tweets': result['keep_tweet_ids'],
                                        'reason': result['reason']
                                    }
                                
                                return {
                                    'action': 'keep_all',
                                    'selected_tweets': [t['id'] for t in tweets],
                                    'reason': result['reason']
                                }
                            else:
                                error_text = await response.text()
                                logger.error(f"API error (attempt {attempt + 1}): {response.status} - {error_text}")
                                
                except Exception as e:
                    logger.error(f"API call failed (attempt {attempt + 1}): {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        # On final retry, keep all tweets
                        return {
                            'action': 'keep_all',
                            'selected_tweets': [t['id'] for t in tweets],
                            'reason': "API failed, keeping all tweets"
                        }
                        
            return None
                        
        except Exception as e:
            logger.error(f"Error analyzing tweet similarity: {str(e)}")
            return None
            
    def _handle_repost_or_quote(self, tweets):
        """Pre-process tweets to handle reposts and quote tweets"""
        try:
            # First handle reposts
            for tweet in tweets:
                if tweet.get('isRepost') and tweet.get('repostedContent'):
                    original_text = tweet.get('repostedContent', {}).get('text', '')
                    original_author = tweet.get('repostedContent', {}).get('authorHandle', '')
                    
                    # Find original tweet in the group
                    for other_tweet in tweets:
                        if not other_tweet.get('isRepost') and (
                            other_tweet['text'] == original_text or 
                            other_tweet['authorHandle'] == original_author
                        ):
                            logger.info(f"Found original tweet for repost: {other_tweet['id']}")
                            return {
                                'action': 'select',
                                'selected_tweets': [other_tweet['id']],
                                'reason': "Selected original tweet over repost"
                            }
                    
                    # If original not found, keep the repost
                    logger.info(f"Original not found, keeping repost: {tweet['id']}")
                    return {
                        'action': 'select',
                        'selected_tweets': [tweet['id']],
                        'reason': "Kept repost as original not found"
                    }
                    
            # Then handle quote tweets
            for tweet in tweets:
                if tweet.get('isQuoteRetweet') and tweet.get('quotedContent'):
                    quoted_text = tweet.get('quotedContent', {}).get('text', '')
                    quoted_author = tweet.get('quotedContent', {}).get('authorHandle', '')
                    
                    # Find quoted tweet in the group
                    for other_tweet in tweets:
                        if other_tweet['text'] == quoted_text or other_tweet['authorHandle'] == quoted_author:
                            # Check if quote adds significant new information
                            quote_words = set(tweet['text'].split())
                            quoted_words = set(quoted_text.split())
                            new_words = quote_words - quoted_words
                            
                            if len(new_words) > len(quoted_words) * 0.3:  # Quote adds >30% new content
                                logger.info(f"Quote tweet adds significant info: {tweet['id']}")
                                return {
                                    'action': 'keep_all',
                                    'selected_tweets': [tweet['id'], other_tweet['id']],
                                    'reason': "Quote tweet adds significant new information"
                                }
                            else:
                                logger.info(f"Selected original over quote: {other_tweet['id']}")
                                return {
                                    'action': 'select',
                                    'selected_tweets': [other_tweet['id']],
                                    'reason': "Selected original tweet over quote with minimal addition"
                                }
            
            # No reposts or quotes found
            return None
            
        except Exception as e:
            logger.error(f"Error handling repost/quote: {str(e)}")
            return None
            
    async def group_tweets(self, tweets):
        """Group tweets by similar content"""
        try:
            # Split tweets into reposts and non-reposts
            repost_tweets = [t for t in tweets if t.get('isRepost')]
            non_repost_tweets = [t for t in tweets if not t.get('isRepost')]
            final_tweets = []
            
            # Handle reposts first
            for repost in repost_tweets:
                repost_result = self._handle_repost_or_quote([repost] + non_repost_tweets)
                if repost_result:
                    selected = [t for t in tweets if t['id'] in repost_result['selected_tweets']]
                    final_tweets.extend(selected)
                    # Remove selected tweets from non_repost pool
                    non_repost_tweets = [t for t in non_repost_tweets if t['id'] not in repost_result['selected_tweets']]
            
            # Now analyze remaining non-repost tweets for similarity
            if len(non_repost_tweets) > 1:
                result = await self.analyze_similarity(non_repost_tweets)
                if result and result['action'] == 'select':
                    selected = [t for t in non_repost_tweets if t['id'] in result['selected_tweets']]
                    final_tweets.extend(selected)
                else:
                    final_tweets.extend(non_repost_tweets)
            else:
                final_tweets.extend(non_repost_tweets)
            
            logger.info(f"Final tweet count: {len(final_tweets)}")
            return [final_tweets]
                
        except Exception as e:
            logger.error(f"Error in group_tweets: {str(e)}")
            return [[t] for t in tweets]  # On error, keep all tweets separate
            
    def _is_valid_tweet(self, tweet):
        """Validate tweet structure and content"""
        try:
            # Check required fields
            required_fields = ['id', 'text', 'authorHandle', 'url']
            if not all(field in tweet for field in required_fields):
                return False
                
            # Check text content
            if not tweet['text'] or len(tweet['text'].split()) < 2:
                return False
                
            # Check for valid ID
            if not tweet['id'] or not str(tweet['id']).strip():
                return False
                
            # Check for valid author
            if not tweet['authorHandle'] or not str(tweet['authorHandle']).strip():
                return False
                
            return True
                
        except Exception as e:
            logger.error(f"Error validating tweet: {str(e)}")
            return False
            
    async def process_chunk(self, chunk):
        """Process a chunk of tweets"""
        try:
            # Group tweets in chunk
            tweet_groups = await self.group_tweets(chunk)
            refined_tweets = []
            
            # Process each group
            for group in tweet_groups:
                # Validate tweets in group
                valid_tweets = [t for t in group if self._is_valid_tweet(t)]
                if not valid_tweets:
                    logger.debug("No valid tweets in group, skipping")
                    continue
                    
                # For single tweets, just add them if valid
                if len(valid_tweets) == 1:
                    refined_tweets.append(valid_tweets[0])
                    continue
                    
                # Analyze group for similarity
                result = await self.analyze_similarity(valid_tweets)
                if result:
                    if result['action'] == 'keep_all':
                        refined_tweets.extend(valid_tweets)
                        logger.debug(f"Keeping all {len(valid_tweets)} tweets (unique content)")
                    elif result['action'] == 'select':
                        selected = [t for t in valid_tweets if t['id'] in result['selected_tweets']]
                        refined_tweets.extend(selected)
                        logger.debug(f"Selected {len(selected)}/{len(valid_tweets)} tweets: {result['reason'][:100]}...")
            
            return refined_tweets
            
        except Exception as e:
            logger.error(f"Error processing chunk: {str(e)}")
            return []
            
    async def process_column(self, tweets):
        """Process tweets in a column using chunks"""
        refined_tweets = []
        chunks = [tweets[i:i + self.chunk_size] for i in range(0, len(tweets), self.chunk_size)]
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Column chunk {i+1}/{len(chunks)}: Processing {len(chunk)} tweets")
            chunk_results = await self.process_chunk(chunk)
            refined_tweets.extend(chunk_results)
            
            if i < len(chunks) - 1:
                await asyncio.sleep(1)
                
        return refined_tweets
            
    async def refine_tweets(self, date_str=None):
        """Process and refine tweets for a given date"""
        try:
            if not date_str:
                date_str = datetime.now().strftime('%Y%m%d')
                
            logger.info(f"Starting refinement for {date_str}")
            
            file_path = self.processed_dir / f'processed_tweets_{date_str}.json'
            if not file_path.exists():
                logger.error(f"No processed tweets found for {date_str}")
                return
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            refined_data = {
                'date': date_str,
                'total_tweets': 0,
                'columns': {}
            }
            
            # Process each column
            for column_id, tweets in data['columns'].items():
                if not tweets:
                    logger.debug(f"Column {column_id}: Empty")
                    continue
                    
                logger.info(f"Column {column_id}: Processing {len(tweets)} tweets")
                refined_tweets = await self.process_column(tweets)
                refined_data['columns'][column_id] = refined_tweets
                refined_data['total_tweets'] += len(refined_tweets)
                
                logger.info(f"Column {column_id}: Refined {len(tweets)} → {len(refined_tweets)} tweets")
                
                if int(column_id) < len(data['columns']) - 1:
                    await asyncio.sleep(5)
            
            # Save refined data
            with open(file_path, 'w') as f:
                json.dump(refined_data, f, indent=2)
                
            logger.info(f"Refinement complete: {data['total_tweets']} → {refined_data['total_tweets']} tweets")
            
        except Exception as e:
            logger.error(f"Error during refinement: {str(e)}")
            
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    # Get date to process
    import sys
    date_to_process = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y%m%d')
    
    # Load config and run refiner
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'deepseek_api_key': os.getenv('DEEPSEEK_API_KEY')
    }
    
    refiner = TweetRefiner(config)
    asyncio.run(refiner.refine_tweets(date_to_process)) 