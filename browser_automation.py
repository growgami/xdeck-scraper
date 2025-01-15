from playwright.async_api import async_playwright
import logging
import json
from pathlib import Path
import asyncio
import random

logger = logging.getLogger(__name__)

class BrowserAutomation:
    def __init__(self, config):
        self.config = config
        self.browser = None
        self.context = None
        self.page = None
        self.storage_state_path = Path("data/session/auth.json")
        
    async def human_type(self, element, text):
        """Type text with human-like delays"""
        for char in text:
            await element.type(char, delay=random.uniform(50, 100))
            await asyncio.sleep(random.uniform(0.01, 0.05))
            
    async def random_delay(self, min_seconds=1, max_seconds=3):
        """Add random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
        
    async def init_browser(self):
        """Initialize browser"""
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,  # For testing
                args=['--start-maximized']  # Start maximized
            )
            
            # Try to load existing session with larger viewport
            if self.storage_state_path.exists():
                self.context = await self.browser.new_context(
                    storage_state=str(self.storage_state_path),
                    viewport={'width': 1920, 'height': 1080}  # Full HD size
                )
                logger.info("Loaded existing session")
            else:
                self.context = await self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080}  # Full HD size
                )
            
            self.page = await self.context.new_page()
            
            # Set window state to maximized
            await self.page.evaluate("window.moveTo(0, 0)")
            await self.page.evaluate("window.resizeTo(screen.width, screen.height)")
            
            logger.info("Browser initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            return False
            
    async def check_login_status(self):
        """Check if already logged in"""
        try:
            logged_in = await self.page.get_by_test_id("logged-in-view").is_visible()
            return logged_in
        except Exception:
            return False
            
    async def handle_login(self):
        """Handle the Twitter login process"""
        try:
            # Navigate to Twitter
            await self.page.goto("https://pro.twitter.com")
            await self.random_delay(2, 4)
            logger.info("Navigated to Twitter")
            
            # Check if already logged in
            if await self.check_login_status():
                logger.info("Already logged in")
                await self.navigate_to_tweetdeck()
                return True
                
            # Click login button
            await self.random_delay(1, 2)
            await self.page.get_by_role("link", name="Log in").click()
            logger.info("Clicked login button")
            
            # Enter username
            await self.random_delay()
            username_input = await self.page.wait_for_selector('input[autocomplete="username"]')
            await self.human_type(username_input, self.config['twitter_username'])
            await self.random_delay(0.5, 1.5)
            await self.page.keyboard.press('Enter')
            logger.info("Entered username")
            
            # Wait for either verification or password step
            await self.random_delay(2, 3)
            try:
                # Check for the exact text from the verification screen
                verification_text = "Enter your phone number or username"
                verification_element = await self.page.get_by_text(verification_text, exact=True).is_visible(timeout=10000)
                
                if verification_element:
                    logger.info("Unusual activity screen detected")
                    # Wait for the input field and click it first
                    verification_input = await self.page.wait_for_selector('input[name="text"]', timeout=10000)
                    await verification_input.click()
                    await self.random_delay(0.5, 1)
                    
                    # Type the verification code instead of username
                    await self.human_type(verification_input, self.config['twitter_2fa'])
                    await self.random_delay(0.5, 1)
                    await self.page.keyboard.press('Enter')
                    
                    logger.info("Submitted verification code")
                    await self.random_delay(2, 3)
            except Exception as e:
                logger.info(f"No verification needed or already passed: {str(e)}")
            
            # Handle 2FA if needed
            try:
                verification_code_input = await self.page.wait_for_selector('input[autocomplete="one-time-code"]', timeout=10000)
                await self.random_delay()
                await self.human_type(verification_code_input, self.config['twitter_2fa'])
                await self.random_delay(0.5, 1)
                await self.page.keyboard.press('Enter')
                logger.info("Entered 2FA code")
                await self.random_delay(2, 3)
            except Exception as e:
                logger.info(f"No 2FA needed: {str(e)}")
            
            # Enter password
            await self.random_delay()
            password_input = await self.page.wait_for_selector('input[name="password"]', timeout=10000)
            await self.human_type(password_input, self.config['twitter_password'])
            await self.random_delay(0.5, 1.5)
            await self.page.keyboard.press('Enter')
            logger.info("Entered password")
            
            # Wait for login to complete and verify
            await self.page.wait_for_selector('[data-testid="logged-in-view"]', timeout=60000)
            
            # Store the session
            await self.store_session()
            
            # Navigate to TweetDeck
            await self.navigate_to_tweetdeck()
            
            logger.info("Successfully logged in")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False
            
    async def navigate_to_tweetdeck(self):
        """Navigate to the specified TweetDeck URL"""
        try:
            # Check if we're already on TweetDeck
            current_url = self.page.url
            if self.config['tweetdeck_url'] in current_url:
                logger.info("Already on TweetDeck")
                return True
                
            logger.info(f"Navigating to TweetDeck URL: {self.config['tweetdeck_url']}")
            await self.page.goto(self.config['tweetdeck_url'], timeout=60000)
            
            # Verify we're on the right URL
            current_url = self.page.url
            if self.config['tweetdeck_url'] in current_url:
                logger.info("Successfully navigated to TweetDeck")
                return True
            else:
                logger.error(f"Navigation failed, on wrong URL: {current_url}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to navigate to TweetDeck: {str(e)}")
            return False
            
    async def store_session(self):
        """Store the browser session"""
        try:
            # Create session directory if it doesn't exist
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Store the session state
            await self.context.storage_state(path=str(self.storage_state_path))
            logger.info("Session stored successfully")
            
        except Exception as e:
            logger.error(f"Failed to store session: {str(e)}")
            
    async def close(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        logger.info("Browser closed") 