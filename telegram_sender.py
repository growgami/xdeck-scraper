import logging
import html
from telegram import Bot
from telegram.constants import ParseMode
import asyncio
import os
from pathlib import Path
import json
from datetime import datetime
from dotenv import load_dotenv
import re

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramSender:
    def __init__(self, bot_token):
        if not bot_token:
            raise ValueError("Bot token is required")
        self.bot = Bot(token=bot_token)
        
    def format_text(self, text):
        """Format text with HTML tags according to instructions"""
        # Split text into lines
        lines = text.split('\n')
        formatted_lines = []
        
        for line in lines:
            if not line.strip():
                formatted_lines.append(line)
                continue
                
            # Format header (Date - Category Rollup)
            if ' - ' in line and 'Rollup' in line:
                line = f"<u><b><i>{html.escape(line)}</i></b></u>"
            
            # Format subcategory (ends with emoji)
            elif line.strip().endswith('📌'):
                # Remove emoji and format
                line = line.replace('📌', '').strip()
                line = f"<u><b>{html.escape(line)}</b></u>"
            
            # Format tweet lines (author: summary url)
            elif ': ' in line and 'http' in line:
                try:
                    # Split into author and rest
                    author, rest = line.split(': ', 1)
                    # Split rest into summary and url
                    summary, url = rest.rsplit(' ', 1)
                    
                    # Escape HTML special characters
                    author = html.escape(author)
                    summary = html.escape(summary)
                    
                    # Format with author in bold and summary as hyperlink
                    line = f"<b>{author}</b>: <a href='{url}'>{summary}</a>"
                except Exception as e:
                    logger.error(f"Failed to format tweet line: {line}")
                    logger.error(f"Error: {str(e)}")
                    formatted_lines.append(line)
                    continue
            
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
        
    async def send_message(self, channel_id, message, max_retries=3):
        """Send formatted message to Telegram channel with retry logic"""
        if not channel_id:
            raise ValueError("Channel ID is required")
            
        logger.info(f"Attempting to send message to channel {channel_id}")
        logger.debug(f"Message content: {message[:100]}...")  # Log first 100 chars
        
        # Format the message with HTML tags
        formatted_message = self.format_text(message)
        
        for attempt in range(max_retries):
            try:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=formatted_message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                logger.info(f"Message sent to channel {channel_id}")
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to send message after {max_retries} attempts")
                    logger.error(f"Last error: {str(e)}")
                    return False
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                await asyncio.sleep(5 * (attempt + 1))  # Exponential backoff

async def test_sender():
    try:
        # Load environment variables
        load_dotenv()
        
        # Validate environment variables
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        test_channel_id = os.getenv('TELEGRAM_TEST_CHANNEL_ID')
        
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        if not test_channel_id:
            raise ValueError("TELEGRAM_TEST_CHANNEL_ID not found in environment variables")
            
        logger.info("Environment variables validated")
        
        # Load actual summaries
        date_str = datetime.now().strftime('%Y%m%d')
        summaries_file = Path('data/summaries') / f'summaries_{date_str}.json'
        
        logger.info(f"Looking for summaries file: {summaries_file}")
        
        if not summaries_file.exists():
            raise FileNotFoundError(f"No summaries found for {date_str}")
            
        logger.info("Loading summaries file")
        with open(summaries_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                summaries = data.get('summaries', {})
                logger.debug(f"Loaded JSON structure: {str(summaries)[:200]}...")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {str(e)}")
                raise
            
        if not summaries:
            logger.info("No summaries found in file, skipping send")
            return
            
        logger.info(f"Loaded {len(summaries)} categories")
        
        # Initialize sender
        sender = TelegramSender(bot_token)
        
        # Send each category's summary to test channel
        for i, (category_name, category_data) in enumerate(summaries.items(), 1):
            try:
                logger.info(f"Processing category {i}/{len(summaries)}: {category_name}")
                
                # Check if category has any tweets in subcategories
                subcategories = category_data.get('subcategories', {})
                has_tweets = False
                for tweets in subcategories.values():
                    if tweets:  # If there are any tweets in this subcategory
                        has_tweets = True
                        break
                
                if not has_tweets:
                    logger.info(f"No tweets found in category {category_name}, skipping")
                    continue
                
                # Use the pre-formatted text directly
                message = category_data.get('text', '')
                if not message:
                    logger.warning(f"No text found for category: {category_name}")
                    continue
                
                # Skip if message only contains the header
                if len(message.split('\n')) <= 2:
                    logger.info(f"Category {category_name} only contains header, skipping")
                    continue
                
                success = await sender.send_message(
                    channel_id=test_channel_id,
                    message=message
                )
                
                if not success:
                    logger.error(f"Failed to send message for category: {category_name}")
                    continue
                    
                # Delay between messages
                if i < len(summaries):  # Don't delay after last message
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to process category {category_name}: {str(e)}")
                continue
        
        logger.info("Test completed successfully")
        
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_sender()) 