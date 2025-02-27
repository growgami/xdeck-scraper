#### Project Overview
- This project is a service that scrapes the latest tweets from tweetdeck or pro.twitter.com and stores them into local json files. This data is then used to generate AI News Summaries of significant news or alphas for specific categories for that day. It uses LLMs to generate the summaries and sends them to specific telegram channels for each category.
- The application will be written using Python. It will be deployed on a vultr server with 2 cores and 2GB of RAM.

# Core Functionalities
- The application will have the following core functionalities:
    1. Browser Automation
        - Browser is headless and will be launched on a ubuntu server.
        - Given a specific pro.twitter.com url for specific tweetdeck decks, the application will use playwright to automate logging into the provided account. Flow is as follows:
            - check if already logged in by looking for data-testid="logged-in-view"
            - if not logged in, look for the login button
            - look for the username input
            - type in the username from the .env file
            - enter
            - check for verification
            - type in the verification code from the .env file
            - enter
            - look for the password input
            - type in the password from the .env file
            - enter
            - verify we are on tweetdeck by looking for data-testid="logged-in-view"
            - store the successful login session
        - It should handle the login process and any necessary authentication steps.
        - It should be able to store and restore the session state so that it can resume from where it left off.
    2. Scraping Tweets
        - The application will identify the columns present in the current deck. It will then scrape tweets and continuously monitor for new tweets to scrape. The flow for this process is as follows:
            - Identify all columns present on the current deck url
            - Scrape all tweets loaded in each column
            - save tweets to a per column json file
            - get the tweet id of the latest tweets per column
            - save these to a latest_tweets.json file
            - continuously check the first tweet of each column
                - if the tweet is not the same as the latest tweet in the latest_tweets.json file, then scrape the tweet and save it to the json file.
            - the application will scrape every 100ms
    3. Data Processing
        - On a designated time, daily, the application will process the data in the following ways:
            - It will deduplicate the tweets in the columns based on the tweet id.
            - It will remove tweets without any text.
            - It will remove tweets with text that are less than 2 words.
            - It will normalize special characters and symbols from the tweets.
            - It will format the tweets data into a structured json format.
            - It will combine the column jsons into a single json file.
    4. AI Tweet Scoring
        - The application will use an Deepseek LLM to score the tweets in the processed json file to see if they are relevant to the category.
        - Each column is mapped to a category.
        - There will be the following categories:
            - NEAR Ecosystem
            - Polkadot Ecosystem
            - Arbitrum Ecosystem
            - IOTA Ecosystem
            - AI Agents
            - DefAI
        - Tweets will be scored based on the following criteria:
            - Relevance to the category
            - Significance of the news
            - Potential impact of the news
            - Relevance to the category
        - It will only keep the tweets with a score greater than 0.7.
        - The application will then update the processed json file, keeping only the tweets with a score greater than 0.7.
    5. AI Tweet Refining
        - The application will use an LLM to scan the tweets and deduplicate or combine them based on the tweet text.
            - It will deduplicate the tweets based on the tweet text and choose the most relevant tweet for each column if the tweets have different tweet ids.
            - It will combine tweets that are of similar content and column into a single tweet if they have the same tweet id.
        - It will then update the processed json file with the refined tweets.
    6. AI News Filtering
        - The application will use an LLM to filter the tweets for each category.
        - It will use the refined tweets to create a news summary for each category.
        - It will let the LLM determine the subcategories for each category based on the tweets in the processed json file. There will be a maximum of 5 subcategories for each category.
        - Only push a subcategory if there are tweets in that subcategory.
        - There should be at least 3 tweet in each subcategory. If there are less than 3 tweets, add to Other Updates subcategory.
        - It will follow a specific format for the summaries. The format is as follows:
            - [Date] - [Category] Rollup
            - [Subcategory] [Emoji]
            - [Author]: [Summary] [Tweet URL]
            - [Author]: [Summary] [Tweet URL]
            - [Subcategory] [Emoji]
            - [Author]: [Summary] [Tweet URL]
            - [Author]: [Summary] [Tweet URL]
            - [Subcategory] [Emoji]
            - [Author]: [Summary] [Tweet URL]
            - [Author]: [Summary] [Tweet URL]
    7. Telegram Channel Sending
        - The sending service will be handling formatting the text of the summaries using HTML.
        - It will format the summaries via the following:
            - Date - Category Rollup will be underlined , bold, and italic.
            - Subcategory will be in underlined and in bold.
            - Author will be in bold and have - before author name.
            - Summary will be a hyperlink to the tweet using the Tweet Link.
        - The application will send the news summaries for each category to their respective telegram channels using channel IDs.
        - It will send the news summaries to the telegram channels at 12:00 AM GMT.
    8. Error Handling
        - The application will handle errors and log them to a file for that session.
        - It will log the error, the time it occurred, and the error message.
        - Error logging will be explicit and detailed.
        - There will be error handling for all the core functionalities.
        - It should have retry logic for all the core functionalities.
        - It should have exponential backoff for all the core functionalities.
    9. Garbage Collection
        - The application will need to be able to handle the load of scraping and sending the news summaries.
        - The application will need to be optimized for performance and memory usage.
        - The application need to have memory cleanup and garbage collection for necessary processes.

# Documentation

# Current File Structure


# Important Implementation Notes

1. Service Organization:
   - Each service is self-contained with its own types and interfaces
   - Services communicate through well-defined interfaces
   - Each service has a main orchestrator class

2. Configuration:
   - All configuration is centralized in config/
   - Environment-specific configs can be loaded from .env

3. Utilities:
   - Utils are grouped by functionality
   - Each utility is designed to be reusable across services
   - Memory management utilities are separated for clarity

4. Data Organization:
   - Clear separation between raw and processed data
   - Logs are organized by date
   - Summaries are stored separately

5. Entry Point (index.ts):
   - Initializes all services
   - Sets up error handlers
   - Manages scheduling
   - Orchestrates the overall flow

