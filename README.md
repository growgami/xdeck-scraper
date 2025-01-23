# AI Newsletter Bot

An AI-powered news aggregator and summarizer for crypto and web3 content. The service scrapes tweets from Twitter, processes them using AI to generate categorized news summaries, and distributes them through Telegram channels.

## Features

- Automated Twitter scraping using Playwright
- Headless browser optimized for Ubuntu servers
- Continuous tweet monitoring (100ms intervals)
- Per-column JSON storage with latest tweet tracking
- Error handling with exponential backoff retries
- Memory-optimized garbage collection

## Prerequisites

- Python 3.10+
- 2GB RAM minimum
- Twitter account credentials
- TweetDeck URL with configured columns

## Installation

1. Clone the repository
```bash
git clone [repository-url]
cd ai-newsletter
```

2. Create and activate virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers
```bash
playwright install
```

5. Create a `.env` file with the following variables:
```env
# Twitter Credentials
TWITTER_USERNAME="your_twitter_username"
TWITTER_PASSWORD="your_twitter_password"
TWEETDECK_URL="https://tweetdeck.twitter.com/your-deck-url"

# Optional Configuration
MONITOR_INTERVAL=0.1       # Tweet check interval in seconds
MAX_RETRIES=3             # Maximum retries for operations
RETRY_DELAY=2.0           # Base delay between retries
GC_CHECK_INTERVAL=3600    # Garbage collection interval in seconds
```

## Usage

The service will automatically:
- Initialize headless browser and login to TweetDeck
- Identify and track columns from configured URL
- Continuously scrape new tweets (every 100ms)
- Store tweets in per-column JSON files
- Maintain session state between restarts
- Perform automatic garbage collection

## Project Structure

```
ai-newsletter/
├── main.py                 # Main application entry point
├── browser_automation.py   # Browser automation using Playwright
├── tweet_scraper.py        # Tweet scraping functionality
├── garbage_collector.py    # Memory management
├── error_handler.py        # Error handling and retry logic
├── data/                   # Data storage
│   ├── raw/                # Raw scraped tweets by date
│   └── session/            # Browser session data
└── logs/                   # Application logs
```

## License

Copyright © 2024 Growgami. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, transfer, or reproduction of the contents of this software, via any medium, is strictly prohibited.
