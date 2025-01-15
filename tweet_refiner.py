import logging
import json
from pathlib import Path
from datetime import datetime
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class TweetRefiner:
    def __init__(self, config):
        self.config = config
        self.data_dir = Path('data')
        self.processed_dir = self.data_dir / 'processed'
        self.api_key = config['deepseek_api_key']
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        
    async def analyze_similarity(self, tweets_group):
        """Analyze a group of tweets for similarity using Deepseek API"""
        try:
            prompt = f"""
            Analyze these tweets for similarity and make a strict determination about deduplication or combination.

            RULES:
            1. DIFFERENT IDs:
               - Only consider tweets as similar if they convey the EXACT same information
               - When choosing the most relevant tweet:
                 * Prefer tweets with more engagement (likes/retweets)
                 * Prefer tweets from verified accounts
                 * Prefer tweets with more detailed information
                 * Prefer original tweets over reposts

            2. SAME ID:
               - Only combine tweets if they are truly complementary
               - The combined text must be concise and non-redundant
               - Maintain the original meaning and context
               - Do not combine if information conflicts

            Tweets to analyze:
            {json.dumps(tweets_group, indent=2)}

            Return the result in the following JSON format:
            {{
                "action": "keep_single" or "combine",
                "selected_tweets": [list of tweet IDs to keep],
                "combined_text": "combined text if action is combine, otherwise null",
                "reasoning": "detailed explanation of why tweets were combined or which was selected",
                "confidence": 0.0 to 1.0  // How confident are you in this decision
            }}

            If confidence is below 0.9, default to keeping tweets separate.
            """
            
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,  # Lower temperature for more consistent results
                "response_format": {"type": "json_object"},
                "max_tokens": 1000
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
                        
                        # Additional validation of the result
                        if result.get('confidence', 0) < 0.9:
                            logger.info("Confidence too low, keeping tweets separate")
                            return {
                                "action": "keep_single",
                                "selected_tweets": [t['id'] for t in tweets_group],
                                "combined_text": None,
                                "reasoning": "Confidence below threshold, keeping tweets separate",
                                "confidence": result.get('confidence', 0)
                            }
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"API error: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error analyzing tweet similarity: {str(e)}")
            return None
            
    def group_tweets(self, tweets):
        """Group tweets by similar content or same ID"""
        # Create a new processed_tweets set for this group of tweets
        processed_tweets = set()
        groups = []
        
        # Group by ID first
        id_groups = {}
        for tweet in tweets:
            if tweet['id'] in processed_tweets:
                continue
                
            tweet_id = tweet['id']
            if tweet_id not in id_groups:
                id_groups[tweet_id] = []
            id_groups[tweet_id].append(tweet)
            processed_tweets.add(tweet_id)
        
        # Add ID-based groups
        groups.extend(list(id_groups.values()))
        
        # Clear processed_tweets before text similarity grouping
        processed_tweets.clear()
        
        # Find remaining tweets that weren't grouped by ID
        remaining_tweets = [t for t in tweets if t['id'] not in id_groups]
        while remaining_tweets:
            current_tweet = remaining_tweets[0]
            if current_tweet['id'] in processed_tweets:
                remaining_tweets.pop(0)
                continue
                
            similar_group = [current_tweet]
            remaining_tweets.pop(0)
            
            # Find similar tweets
            i = 0
            while i < len(remaining_tweets):
                if self._is_similar_text(current_tweet['text'], remaining_tweets[i]['text']):
                    similar_group.append(remaining_tweets[i])
                    processed_tweets.add(remaining_tweets[i]['id'])
                    remaining_tweets.pop(i)
                else:
                    i += 1
            
            if similar_group:
                groups.append(similar_group)
            processed_tweets.add(current_tweet['id'])
        
        # Clear processed_tweets before returning
        processed_tweets.clear()
        return groups
        
    def _is_similar_text(self, text1, text2, threshold=0.9):  # High threshold for strict matching
        """Check if two texts are similar using strict similarity measure"""
        # Clean and normalize texts
        def normalize_text(text):
            text = text.lower().strip()
            # Remove URLs
            words = [w for w in text.split() if not w.startswith('http')]
            return ' '.join(words)
            
        text1 = normalize_text(text1)
        text2 = normalize_text(text2)
        
        # If either text is empty after normalization, they're not similar
        if not text1 or not text2:
            return False
            
        # Get word sets
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        # If length difference is too large, they're not similar
        if abs(len(words1) - len(words2)) > 3:
            return False
            
        # Calculate Jaccard similarity
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        # Both similarity measures must pass threshold
        jaccard = len(intersection) / len(union)
        
        # Calculate word sequence similarity
        seq1 = text1.split()
        seq2 = text2.split()
        common_sequence = 0
        for i in range(min(len(seq1), len(seq2))):
            if seq1[i] == seq2[i]:
                common_sequence += 1
        sequence_sim = common_sequence / min(len(seq1), len(seq2))
        
        return jaccard >= threshold and sequence_sim >= threshold
            
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
            
    async def refine_tweets(self, date_str=None):
        """Process and refine tweets for a given date"""
        try:
            # Use today's date if none provided
            if not date_str:
                date_str = datetime.now().strftime('%Y%m%d')
                
            logger.info(f"Refining tweets for date: {date_str}")
            
            # Load processed tweets
            file_path = self.processed_dir / f'processed_tweets_{date_str}.json'
            if not file_path.exists():
                logger.error(f"No processed tweets file found for date {date_str}")
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
                logger.info(f"Processing column {column_id} with {len(tweets)} tweets")
                
                # Skip empty columns
                if not tweets:
                    logger.info(f"Skipping empty column {column_id}")
                    continue
                    
                # Group similar tweets
                tweet_groups = self.group_tweets(tweets)
                refined_tweets = []
                
                # Process each group
                for group in tweet_groups:
                    if len(group) > 1:
                        # Validate tweets in group
                        valid_tweets = [t for t in group if self._is_valid_tweet(t)]
                        if not valid_tweets:
                            logger.warning(f"No valid tweets in group, skipping")
                            continue
                            
                        # Analyze group for similarity and combination
                        result = await self.analyze_similarity(valid_tweets)
                        if result:
                            if result['action'] == 'combine' and result.get('confidence', 0) >= 0.9:
                                # Create combined tweet
                                base_tweet = valid_tweets[0].copy()
                                base_tweet['text'] = result['combined_text']
                                base_tweet['combined_from'] = [t['id'] for t in valid_tweets]
                                base_tweet['combination_reason'] = result['reasoning']
                                refined_tweets.append(base_tweet)
                                logger.info(f"Combined {len(valid_tweets)} similar tweets with confidence {result.get('confidence')}")
                            else:
                                # Keep selected tweets
                                for tweet_id in result['selected_tweets']:
                                    tweet = next((t for t in valid_tweets if t['id'] == tweet_id), None)
                                    if tweet:
                                        refined_tweets.append(tweet)
                                logger.info(f"Selected {len(result['selected_tweets'])} tweets from group of {len(valid_tweets)}")
                    else:
                        # Single tweet, validate before keeping
                        if self._is_valid_tweet(group[0]):
                            refined_tweets.append(group[0])
                
                refined_data['columns'][column_id] = refined_tweets
                refined_data['total_tweets'] += len(refined_tweets)
                
                logger.info(f"Refined column {column_id}: {len(tweets)} -> {len(refined_tweets)} tweets")
            
            # Save refined data
            with open(file_path, 'w') as f:
                json.dump(refined_data, f, indent=2)
                
            logger.info(f"Saved {refined_data['total_tweets']} refined tweets to {file_path}")
            
        except Exception as e:
            logger.error(f"Error refining tweets: {str(e)}")
            
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get date to process - either from args or use today's date
    import sys
    date_to_process = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y%m%d')
    
    logger.info(f"Processing tweets for date: {date_to_process}")
    
    # Load config and run refiner
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'deepseek_api_key': os.getenv('DEEPSEEK_API_KEY')
    }
    
    refiner = TweetRefiner(config)
    asyncio.run(refiner.refine_tweets(date_to_process)) 