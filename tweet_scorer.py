import logging
import json
from pathlib import Path
from datetime import datetime
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class TweetScorer:
    def __init__(self, config):
        self.config = config
        self.data_dir = Path('data')
        self.processed_dir = self.data_dir / 'processed'
        self.api_key = config['deepseek_api_key']
        self.api_url = "https://api.deepseek.com/v1/chat/completions"  # Update with actual endpoint
        
        # Category mappings
        self.categories = {
            '0': 'NEAR Ecosystem',
            '1': 'Polkadot Ecosystem',
            '2': 'Arbitrum Ecosystem',
            '3': 'IOTA Ecosystem',
            '4': 'AI Agents',
            '5': 'DefAI'
        }
        
    async def score_tweet(self, tweet, category):
        """Score a tweet for relevance to its category"""
        try:
            # Prepare prompt for scoring
            prompt = self._prepare_scoring_prompt(tweet, category)
            
            # Retry configuration
            max_retries = 3
            base_delay = 2  # Start with 2 second delay
            
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
                                "max_tokens": 500
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
                                
                                # Calculate average score if not provided
                                if 'average_score' not in result:
                                    scores = [
                                        result.get('relevance', 0),
                                        result.get('significance', 0),
                                        result.get('impact', 0),
                                        result.get('ecosystem_relevance', 0)
                                    ]
                                    result['average_score'] = sum(scores) / len(scores)
                                
                                # Add metadata
                                result['tweet_id'] = tweet['id']
                                result['category'] = category
                                
                                # Log success
                                logger.debug(f"Successfully scored tweet {tweet['id']} (avg: {result['average_score']:.2f})")
                                return result
                            else:
                                error_text = await response.text()
                                logger.warning(f"API error on attempt {attempt + 1}: {response.status} - {error_text}")
                                
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on attempt {attempt + 1} for tweet {tweet['id']}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON response on attempt {attempt + 1} for tweet {tweet['id']}: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error on attempt {attempt + 1} for tweet {tweet['id']}: {str(e)}")
                
                # Exponential backoff if not last attempt
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
            
            logger.error(f"Failed to score tweet {tweet['id']} after {max_retries} attempts")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error scoring tweet {tweet['id']}: {str(e)}")
            return None
            
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
            
    async def process_tweets(self, date_str):
        """Process all tweets for a given date"""
        try:
            # Load tweets from processed file
            file_path = self.processed_dir / f'processed_tweets_{date_str}.json'
            if not file_path.exists():
                logger.error(f"No processed tweets file found for date {date_str}")
                return
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Process tweets in smaller chunks to avoid overwhelming the API
            chunk_size = 5
            tasks = []
            
            for column_id, tweets in data['columns'].items():
                # Skip empty columns
                if not tweets:
                    logger.info(f"Skipping empty column {column_id}")
                    continue
                    
                category = self.categories.get(column_id)
                if not category:
                    logger.warning(f"No category mapping found for column {column_id}")
                    continue
                
                # Validate tweets before scoring
                valid_tweets = [t for t in tweets if self._is_valid_tweet(t)]
                if not valid_tweets:
                    logger.warning(f"No valid tweets found in column {column_id}")
                    continue
                    
                logger.info(f"Processing {len(valid_tweets)}/{len(tweets)} valid tweets in column {column_id}")
                
                # Process tweets in chunks
                for i in range(0, len(valid_tweets), chunk_size):
                    chunk = valid_tweets[i:i + chunk_size]
                    chunk_tasks = [self.score_tweet(tweet, category) for tweet in chunk]
                    tasks.extend(chunk_tasks)
                    
                    # Add delay between chunks within a column
                    if i + chunk_size < len(valid_tweets):
                        await asyncio.sleep(2)
                
                # Add delay between columns
                if int(column_id) < len(data['columns']) - 1:
                    await asyncio.sleep(5)
            
            # Process chunks in parallel with semaphore to limit concurrency
            semaphore = asyncio.Semaphore(5)  # More conservative limit on concurrent API calls
            async def score_with_semaphore(task):
                async with semaphore:
                    return await task
            
            logger.info(f"Processing {len(tasks)} tweets in chunks...")
            scores = await asyncio.gather(*[score_with_semaphore(task) for task in tasks])
            
            # Filter and update tweets based on scores
            filtered_data = {
                'date': date_str,
                'total_tweets': 0,
                'columns': {}
            }
            
            for column_id, tweets in data['columns'].items():
                filtered_tweets = []
                for tweet in tweets:
                    # Skip invalid tweets
                    if not self._is_valid_tweet(tweet):
                        continue
                        
                    for score in scores:
                        if score and score.get('tweet_id') == tweet['id']:
                            if score.get('relevance', 0) > 0.7:  # Only keep tweets with high relevance
                                tweet['scores'] = score
                                filtered_tweets.append(tweet)
                            break
                
                if filtered_tweets:
                    filtered_data['columns'][column_id] = filtered_tweets
                    filtered_data['total_tweets'] += len(filtered_tweets)
                    logger.info(f"Kept {len(filtered_tweets)}/{len(tweets)} tweets for column {column_id}")
            
            # Save filtered data
            with open(file_path, 'w') as f:
                json.dump(filtered_data, f, indent=2)
                
            logger.info(f"Saved {filtered_data['total_tweets']} high-scoring tweets to {file_path}")
            
        except Exception as e:
            logger.error(f"Error processing tweets: {str(e)}")
            
    def _prepare_scoring_prompt(self, tweet, category):
        """Prepare the prompt for scoring a tweet"""
        return f"""
        Please analyze this tweet's importance specifically for the {category} category and provide scores in JSON format.

        STRICT SCORING RULES:
        1. Tweet MUST explicitly mention the ecosystem name or its official projects/protocols
        2. Generic blockchain/Web3 mentions are NOT sufficient
        3. Do not make assumptions about project affiliations
        4. Require clear evidence of ecosystem connection
        5. When in doubt, score lower

        Tweet Content:
        Text: {tweet['text']}
        Author: {tweet['authorHandle']}
        {"Quoted content: " + tweet['quotedContent']['text'] if tweet.get('quotedContent') else ""}
        {"Reposted content: " + tweet['repostedContent']['text'] if tweet.get('repostedContent') else ""}

        Scoring criteria:
        1. Relevance (0-1): Does the tweet EXPLICITLY mention {category} or its verified projects? Score 0 if no direct mention.
           - Score 0.9-1.0: Direct mention of ecosystem name + significant update
           - Score 0.7-0.8: Direct mention of verified ecosystem project + update
           - Score 0.0-0.3: Generic blockchain/Web3 content or unverified projects
           - Score 0: No explicit mention of ecosystem or verified projects

        2. Significance (0-1): How important is this verified update for {category}?
           - Must be about confirmed ecosystem projects
           - Score based on concrete impact, not potential
           - Lower score if relationship is unclear

        3. Impact (0-1): What measurable effects will this have on {category}?
           - Require specific metrics or clear outcomes
           - Must directly relate to ecosystem growth
           - Lower score for indirect or assumed benefits

        4. Ecosystem relevance (0-1): How does this contribute to {category}'s development?
           - Must demonstrate clear ecosystem connection
           - Score 0 if relationship is assumed
           - Higher scores only for official integrations/partnerships

        Your reasoning must:
        1. Identify the EXPLICIT mention of ecosystem or verified project
        2. Explain why you're confident about ecosystem connection
        3. Point out any assumptions you made (and lower score accordingly)
        4. Be skeptical of unverified relationships

        EXAMPLE JSON OUTPUT:
        {{
            "relevance": 0.8,
            "significance": 0.7,
            "impact": 0.9,
            "ecosystem_relevance": 0.85,
            "average_score": 0.81,
            "reasoning": "This tweet EXPLICITLY mentions {category} by [exact reference]. The ecosystem connection is verified through [specific evidence]. The impact is clear because [concrete metrics/outcomes]. Note: I assumed [any assumptions] and lowered the score accordingly."
        }}
        """
            
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
    
    # Load config and run scorer
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'deepseek_api_key': os.getenv('DEEPSEEK_API_KEY')
    }
    
    scorer = TweetScorer(config)
    asyncio.run(scorer.process_tweets(date_to_process)) 