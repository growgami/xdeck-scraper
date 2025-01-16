# AI Newsletter Bot

An AI-powered news aggregator and summarizer for crypto and web3 content. The service scrapes tweets from Twitter, processes them using AI to generate categorized news summaries, and distributes them through Telegram channels.

## Features

- Automated Twitter scraping using Playwright
- AI-powered tweet scoring and categorization using DeepSeek API
- Smart news filtering and summarization
- Automated distribution to Telegram channels
- Memory-optimized with garbage collection for 2GB RAM environments
- Scheduled daily summaries at 6 AM UTC

## Prerequisites

- Python 3.10+
- 2GB RAM minimum
- Twitter account with TweetDeck access
- Telegram Bot Token and Channel IDs
- DeepSeek API Key

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
TWITTER_USERNAME=your_username
TWITTER_PASSWORD=your_password
TWITTER_VERIFICATION_CODE=your_2fa_code
TWEETDECK_URL=https://tweetdeck.twitter.com/

# DeepSeek API
DEEPSEEK_API_KEY=your_api_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_POLKADOT_CHANNEL_ID=channel_id
TELEGRAM_IOTA_CHANNEL_ID=channel_id
TELEGRAM_ARBITRUM_CHANNEL_ID=channel_id
TELEGRAM_NEAR_CHANNEL_ID=channel_id
TELEGRAM_AI_AGENT_CHANNEL_ID=channel_id
TELEGRAM_DEFI_CHANNEL_ID=channel_id

# Optional Configuration
MONITOR_INTERVAL=0.1       # Tweet check interval in seconds
MAX_RETRIES=3             # Maximum retries for operations
RETRY_DELAY=2.0           # Base delay between retries
GC_CHECK_INTERVAL=3600    # Garbage collection interval in seconds
```

## Usage

1. Start the bot:
```bash
python main.py
```

The service will automatically:
- Initialize browser and login to TweetDeck
- Scrape tweets continuously from configured columns
- Process and score tweets using DeepSeek API
- Generate daily news summaries at 6 AM UTC
- Send categorized summaries to Telegram channels

## Project Structure

```
ai-newsletter/
├── main.py                 # Main application entry point
├── browser_automation.py   # Browser automation using Playwright
├── tweet_scraper.py       # Tweet scraping functionality
├── data_processor.py      # Raw tweet processing
├── tweet_scorer.py        # Tweet scoring using DeepSeek
├── tweet_refiner.py       # Tweet refinement and deduplication
├── news_filter.py         # News filtering and categorization
├── telegram_sender.py     # Telegram message distribution
├── garbage_collector.py   # Memory management
├── category_mapping.py    # Centralized category configurations
├── error_handler.py       # Error handling and retry logic
├── data/                  # Data storage
│   ├── raw/              # Raw scraped tweets by date
│   ├── processed/        # Processed tweet data
│   ├── summaries/        # Generated summaries
│   └── session/          # Browser session data
└── logs/                 # Application logs
```

## Category Structure

The bot processes tweets for the following ecosystems:
- NEAR Ecosystem
- Polkadot Ecosystem
- Arbitrum Ecosystem
- IOTA Ecosystem
- AI Agents
- DefAI

Each category has specific focus areas and subcategories defined in `category_mapping.py`.

## Deployment

For production deployment, use the provided systemd service:

1. Copy service file:
```bash
sudo cp newsbot.service /etc/systemd/system/
```

2. Create newsbot user and set permissions:
```bash
sudo useradd -r -s /bin/false newsbot
sudo chown -R newsbot:newsbot /opt/ai_newsletter
```

3. Enable and start the service:
```bash
sudo systemctl enable newsbot
sudo systemctl start newsbot
```

## License

Copyright © 2024 Growgami. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, transfer, or reproduction of the contents of this software, via any medium, is strictly prohibited. 