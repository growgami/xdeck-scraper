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
        - It will follow a specific prompt for summarizing the tweets. Prompt will be in #Documentation.
    7. Telegram Channel Sending
        - The sending service will be handling formatting the text of the summaries using HTML.
        - It will format the summaries via the following:
            - Date - Category Rollup will be underlined , bold, and italic.
            - Subcategory will be in underlined and in bold.
            - Author will be in bold.
            - Summary will be a hyperlink to the tweet using the Tweet Link.
        - The application will send the news summaries for each category to their respective telegram channels using channel IDs.
        - It will send the news summaries to the telegram channels at 12:00 AM GMT.
    8. Error Handling
        - The application will handle errors and log them to a file for that day.
        - It will log the error, the time it occurred, and the error message.
        - Error logging will be explicit and detailed.
        - There will be error handling for all the core functionalities.
    9. Garbage Collection
        - The application will be ran in a 2 core 2GB RAM vultr server.
        - The application will need to be able to handle the load of scraping and sending the news summaries.
        - The application will need to be optimized for performance and memory usage.
        - The application need to have memory cleanup and garbage collection for necessary processes.

# Documentation
    1. Prompt for AI News Filtering
        '''
            const response = await this.openai.chat.completions.create({
                model: "gpt-4o-mini",
                messages: [
                    {
                        role: "system",
                        content: `You are a crypto and web3 analyst. Your task is to analyze a dataset of tweets and categorize them based on their **context** and **semantic meaning**. Focus on understanding the deeper intent of each tweet, rather than relying on specific words. 

### **Categorization Rules**
Organize tweets into the following categories:
1. **Development & Technology**: Updates about technical advancements, new feature launches, blockchain concepts, or innovations.
2. **Ecosystem Growth**: Tweets related to partnerships, community growth, adoption milestones, or integrations.
3. **Market & Governance**: Financial updates, tokenomics, governance changes, market trends, or liquidity-related insights.
4. **External Relations**: Collaborations, media coverage, new listings, or mentions outside the ecosystem.
5. **Other Updates**: Tweets that don't fit the above categories but provide relevant information (e.g., events, announcements).
6. **Alerts**: Identify potential scams, phishing attempts, or fake news based on context and cross-references within the dataset.

### **Instructions**
- **Contextual Categorization**: Use the semantic meaning of the tweet to determine the most appropriate category.
- **Combine Related Updates**: If multiple tweets from the same account or related context address the same topic, combine them into a single entry.
- **Detect Scams or Fake News**: Evaluate tweets for signs of phishing, compromised accounts, or unrealistic claims.

### **Summary Rules**
- Keep summaries EXTREMELY concise (max 10-15 words)
- Focus on key facts and actions only
- Remove unnecessary words and context
- Use active voice and present tense
- Include only the most impactful metrics/numbers
- Format: "author: [concise action/update] [URL]"

### **Output Example**
{
    "Development & Technology": [
        "author: Launches new cross-chain bridge with 5s finality [URL]"
    ],
    "Ecosystem Growth": [
        "author: Partners with Microsoft for enterprise blockchain solutions [URL]"
    ],
    "Market & Governance": [
        "author: TVL reaches $500M, up 25% this month [URL]"
    ],
    "External Relations": [
        "author: Featured in Bloomberg article on DeFi innovation [URL]"
    ],
    "Other Updates": [
        "author: Announces virtual hackathon with $100K prizes [URL]"
    ],
    "Alerts": [
        "author: Warning: Fake airdrop campaign detected [URL]"
    ]
}`
                    },
                    {
                        role: "user",
                        content: `Analyze and categorize the following tweets into the structured format described above. Tweets:\n\n${JSON.stringify(tweets, null, 2)}`
                    }
                ],
                temperature: 0.3
            });

            const summary = JSON.parse(response.choices[0].message.content);
            const processedSummary = {
                name: ecosystem,
                subcategories: {}
            };
        '''

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

