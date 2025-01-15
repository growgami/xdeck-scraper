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
        self.max_retries = 3
        self.base_delay = 2  # Base delay in seconds
        
    def format_text(self, text):
        """Format text with HTML tags according to instructions"""
        if not text:
            logger.warning("Received empty text to format")
            return ""
            
        try:
            lines = text.split('\n')
            formatted_lines = []
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                    
                # Format header (Date - Category Rollup)
                if ' - ' in line and 'Rollup' in line:
                    formatted_lines.append(f"<u><b><i>{html.escape(line)}</i></b></u>")
                    i += 1
                    continue
                    
                # Format subcategory with emoji
                if not ':' in line and not line.startswith('http'):
                    # Add newline before subcategory if not first line
                    if formatted_lines:
                        formatted_lines.append('')
                    formatted_lines.append(f"<u><b>{html.escape(line)}</b></u>")
                    i += 1
                    continue
                    
                # Format tweet lines (author: text) with URL on next line
                if ':' in line and not line.startswith('http'):
                    try:
                        author, content = line.split(':', 1)
                        url = ""
                        
                        # Check next line for URL
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith('http'):
                            url = lines[i + 1].strip()
                            i += 2  # Skip both current line and URL line
                        else:
                            i += 1  # Just skip current line
                            
                        # Format with dash, bold author, and hyperlinked content
                        formatted_lines.append(f"- <b>{html.escape(author.strip())}</b>: <a href='{url}'>{html.escape(content.strip())}</a>")
                            
                    except Exception as e:
                        logger.error(f"Failed to format tweet line: {line}")
                        logger.error(f"Error: {str(e)}")
                        formatted_lines.append(line)
                        i += 1
                    continue
                    
                # Keep URLs as is but prevent auto-embedding
                if line.startswith('http'):
                    formatted_lines.append(line.replace('https:', 'https:\u200B'))
                    i += 1
                    continue
                    
                # Default case - keep line as is
                formatted_lines.append(html.escape(line))
                i += 1
                
            return '\n'.join(formatted_lines)
        except Exception as e:
            logger.error(f"Error formatting text: {str(e)}")
            logger.error(f"Original text: {text[:100]}...")  # Log first 100 chars
            raise
        
    async def send_message(self, channel_id: str, text: str) -> bool:
        """Send a message to a Telegram channel with retry logic"""
        if not text or text.isspace():
            logger.info("Empty message, skipping send")
            return False
            
        if not channel_id:
            logger.error("No channel ID provided")
            return False
            
        for attempt in range(self.max_retries):
            try:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    parse_mode='HTML',
                    disable_web_page_preview=True  # Prevent URL previews
                )
                logger.info(f"Successfully sent message to channel {channel_id}")
                return True
                
            except Exception as e:
                delay = self.base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Failed to send message after {self.max_retries} attempts")
                    logger.error(f"Last error: {str(e)}")
                    return False
                    
async def test_sender():
    """Test the TelegramSender"""
    load_dotenv()
    
    try:
        # Validate environment variables
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        test_channel_id = os.getenv('TELEGRAM_TEST_CHANNEL_ID')
        
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        if not test_channel_id:
            raise ValueError("TELEGRAM_TEST_CHANNEL_ID not found in environment variables")
            
        # Get date string for today
        date_str = datetime.now().strftime('%Y%m%d')
        
        # Load summaries
        summaries_file = Path('data') / 'summaries' / f'summaries_{date_str}.json'
        if not summaries_file.exists():
            logger.info(f"No summaries file found for date {date_str}")
            return
            
        try:
            with open(summaries_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not data or not data.get('summaries'):
                logger.info("No summaries found in file, skipping send")
                return
                
            sender = TelegramSender(bot_token)
            
            for category, content in data['summaries'].items():
                try:
                    if not content.get('text'):
                        logger.info(f"No text content for {category}, skipping")
                        continue
                        
                    raw_text = content['text']
                    if not raw_text or raw_text.isspace():
                        logger.info(f"Empty text for {category}, skipping")
                        continue
                        
                    # Format the text with HTML tags before sending
                    formatted_text = sender.format_text(raw_text)
                    if not formatted_text:
                        logger.info(f"Empty formatted text for {category}, skipping")
                        continue
                        
                    success = await sender.send_message(
                        channel_id=test_channel_id,
                        text=formatted_text
                    )
                    
                    if success:
                        logger.info(f"Successfully sent {category} summary")
                    else:
                        logger.error(f"Failed to send {category} summary")
                        
                    await asyncio.sleep(2)  # Delay between messages
                    
                except Exception as e:
                    logger.error(f"Error processing category {category}: {str(e)}")
                    continue  # Continue with next category even if one fails
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse summaries file: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error in test_sender: {str(e)}")
        logger.error(f"Error details: {str(e.__class__.__name__)}")
        import traceback
        logger.error(traceback.format_exc())
        raise  # Re-raise to ensure the script exits with error

if __name__ == "__main__":
    asyncio.run(test_sender()) 