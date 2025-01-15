# AI Newsletter

An AI-powered news aggregator and summarizer for crypto and web3 content. The service scrapes tweets from Twitter, processes them using AI to generate categorized news summaries, and distributes them through Telegram channels.

## Features

- Automated Twitter scraping using Playwright
- AI-powered tweet categorization and scoring
- Smart news summarization using GPT-4
- Automated distribution to Telegram channels
- Memory-optimized for resource-constrained environments

## Prerequisites

- Node.js 18+
- NPM 8+
- 2GB RAM minimum
- Twitter Pro account
- Telegram Bot Token and Channel IDs
- OpenAI API Key

## Installation

1. Clone the repository
```bash
git clone [repository-url]
cd ai-newsletter
```

2. Install dependencies
```bash
npm install
```

3. Create a `.env` file with the following variables:
```env
# Twitter Credentials
TWITTER_USERNAME=your_username
TWITTER_PASSWORD=your_password

# OpenAI
OPENAI_API_KEY=your_api_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_POLKADOT_CHANNEL_ID=channel_id
TELEGRAM_IOTA_CHANNEL_ID=channel_id
TELEGRAM_ARBITRUM_CHANNEL_ID=channel_id
TELEGRAM_NEAR_CHANNEL_ID=channel_id
TELEGRAM_AI_AGENTS_CHANNEL_ID=channel_id
TELEGRAM_CRYPTO_NEWS_CHANNEL_ID=channel_id
```

## Usage

1. Build the project:
```bash
npm run build
```

2. Start the service:
```bash
npm start
```

The service will automatically:
- Scrape tweets at regular intervals
- Process and categorize tweets using AI
- Generate daily news summaries
- Send summaries to Telegram channels at 00:00 GMT

## Project Structure

```
project-root/
├── src/                      # Source code
│   ├── services/            # Core services
│   ├── config/              # Configuration files
│   ├── utils/               # Utility functions
│   └── index.ts             # Entry point
├── data/                    # Data storage
│   ├── tweets/              # Raw and processed tweets
│   ├── summaries/           # Generated summaries
│   └── logs/                # Application logs
└── tests/                   # Test files
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 