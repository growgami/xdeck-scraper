import { Builder, By, until, Key } from 'selenium-webdriver';
import * as firefox from 'selenium-webdriver/firefox.js';
import * as path from 'path';
import { promises as fsPromises } from 'fs';
import { existsSync } from 'fs';
import { StorageService } from './storageService.js';
import { config } from '../config/config.js';

export class TweetScraper {
    constructor(options = {}) {
        this.driver = null;
        this.isLoggedIn = false;
        this.outputFile = config.paths.tweets;
        this.latestTweets = {}; // Store latest tweet IDs per column
        this.lastMemoryCheck = Date.now();
        this.memoryCheckInterval = 5 * 60 * 1000; // 5 minutes
        
        // Core options
        this.options = {
            headless: true, // Force headless mode
            cookiesPath: options.cookiesPath ?? config.paths.cookies,
            outputPath: options.outputPath ?? this.outputFile,
            latestTweetsPath: options.latestTweetsPath ?? path.join(config.paths.data, 'latest_tweets.json'),
            onTweetFound: options.onTweetFound
        };

        this.storageService = new StorageService();
    }

    async initialize() {
        try {
            await this.loadLatestTweets();
            
            // Setup Firefox driver with memory optimizations
            const options = new firefox.Options();
            
            if (this.options.headless) {
                options.addArguments('-headless');
                options.addArguments('--width=1920');
                options.addArguments('--height=1080');
                options.addArguments('--disable-gpu');
                options.addArguments('--no-sandbox');
                options.addArguments('--disable-dev-shm-usage');
                // Add memory optimization flags
                options.addArguments('--memory-pressure-off');
                options.addArguments('--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies');
                options.addArguments('--js-flags="--max-old-space-size=512"');
            }

            this.driver = await new Builder()
                .forBrowser('firefox')
                .setFirefoxOptions(options)
                .build();

            await this.driver.manage().window().setRect({ width: 1920, height: 1080 });
            
            // Set reasonable timeouts
            await this.driver.manage().setTimeouts({
                implicit: 10000,
                pageLoad: 30000,
                script: 30000
            });

            if (existsSync(this.options.cookiesPath)) {
                await this.loadCookies();
            }

            return true;
        } catch (error) {
            console.error('Error initializing browser:', error);
            return false;
        }
    }

    async loadCookies() {
        try {
            if (!existsSync(this.options.cookiesPath)) {
                console.error('Cookies file not found:', this.options.cookiesPath);
                return false;
            }

            const cookieData = await fsPromises.readFile(this.options.cookiesPath, 'utf8');
            const cookies = cookieData.split('\n')
                .filter(line => line && !line.startsWith('#'))
                .map(line => {
                    const [,,,,,name, value] = line.split('\t');
                    return { name, value };
                })
                .filter(cookie => cookie.name && cookie.value);

            console.log(`Loading ${cookies.length} Twitter cookies from file`);

            for (const cookie of cookies) {
                try {
                    await this.driver.manage().addCookie({
                        ...cookie,
                        domain: '.twitter.com',
                        path: '/',
                        secure: true,
                        sameSite: 'None'
                    });
                } catch (error) {
                    console.error(`Failed to add cookie ${cookie.name}:`, error.message);
                }
            }

            return true;
        } catch (error) {
            console.error('Error loading cookies:', error);
            return false;
        }
    }

    async login() {
        try {
            console.log('Starting TweetDeck login process...');

            // Navigate to TweetDeck
            await this.driver.get('https://tweetdeck.twitter.com/');
            console.log('Navigated to TweetDeck');

            // Load cookies
            if (!await this.loadCookies()) {
                console.error('Failed to load cookies file');
                return false;
            }

            // Refresh page to apply cookies
            console.log('Refreshing page to apply cookies...');
            await this.driver.navigate().refresh();
            await this.driver.sleep(5000);

            // Verify TweetDeck loaded successfully with longer timeout
            if (await this.verifyTweetDeckLoaded(30000)) {
                console.log('Successfully logged in using cookies');
                this.isLoggedIn = true;
                return true;
            }

            console.log('Cookie login failed, manual login required');
            return false;
        } catch (error) {
            console.error('Login failed:', error);
            return false;
        }
    }

    async verifyTweetDeckLoaded(timeout = 30000) {
        try {
            console.log('Verifying TweetDeck is loaded...');
            
            // First wait for any login redirect to complete
            await this.driver.sleep(5000);

            // Wait for the main TweetDeck container
            await this.driver.wait(
                until.elementLocated(By.css('div[data-testid="multi-column-layout-column-content"]')),
                timeout,
                'Timed out waiting for TweetDeck layout'
            );

            // Wait for at least one column to load
            await this.driver.wait(
                until.elementLocated(By.css('div[data-testid="multi-column-layout-column-content"]')),
                timeout,
                'Timed out waiting for TweetDeck columns'
            );
            
            // Wait a moment for any dynamic content
            await this.driver.sleep(2000);

            // Verify we can find columns
            const columns = await this.driver.findElements(
                By.css('div[data-testid="multi-column-layout-column-content"]')
            );
            
            if (columns.length > 0) {
                console.log(`TweetDeck verified - found ${columns.length} columns`);
                return true;
            }
            
            console.log('TweetDeck verification failed - no columns found');
            return false;
        } catch (error) {
            console.error('TweetDeck verification failed:', error.message);
            return false;
        }
    }

    async findColumns() {
        try {
            let columns = await this.driver.findElements(
                By.css('div[data-testid="multi-column-layout-column-content"]')
            );

            if (columns.length === 0) {
                await this.driver.sleep(8000);
                columns = await this.driver.findElements(
                    By.css('div[data-testid="multi-column-layout-column-content"]')
                );
            }

            return columns;
        } catch (error) {
            console.error('Error finding columns:', error);
            return [];
        }
    }

    async processColumn(column, columnIndex) {
        try {
            const firstTweet = await this.findNewestTweet(column);
            if (!firstTweet) return null;

            const tweetData = await this.extractTweetData(firstTweet);
            if (!tweetData || !tweetData.id) return null;

            if (!this.isNewTweet(columnIndex, tweetData.id, tweetData.timestamp)) {
                return null;
            }

            tweetData.columnIndex = columnIndex;

            // Optimize media handling
            if (tweetData.hasMedia) {
                // Filter media first to reduce processing
                tweetData.media.images = tweetData.media.images.filter(img => img.isRetweet);
                tweetData.media.videos = tweetData.media.videos.filter(vid => vid.isRetweet);
                tweetData.media.gifs = tweetData.media.gifs.filter(gif => gif.isRetweet);
                
                // Update hasMedia flag based on filtered media
                tweetData.hasMedia = tweetData.media.images.length > 0 || 
                                   tweetData.media.videos.length > 0 || 
                                   tweetData.media.gifs.length > 0;

                // Process media in smaller batches
                if (tweetData.hasMedia) {
                    const BATCH_SIZE = 3; // Process 3 media items at a time
                    const mediaPromises = [];
                    
                    // Process images in batches
                    for (let i = 0; i < tweetData.media.images.length; i += BATCH_SIZE) {
                        const batch = tweetData.media.images.slice(i, i + BATCH_SIZE);
                        const batchPromises = batch.map(img => 
                            this.verifyMediaUrl(img.url)
                                .catch(() => {
                                    console.log(`Image failed to load: ${img.url}`);
                                    return false;
                                })
                        );
                        
                        const results = await Promise.all(batchPromises);
                        
                        // Filter out failed images from this batch
                        for (let j = 0; j < batch.length; j++) {
                            if (!results[j]) {
                                const index = i + j;
                                tweetData.media.images[index] = null;
                            }
                        }
                        
                        // Small delay between batches to prevent memory spikes
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }
                    
                    // Clean up null entries
                    tweetData.media.images = tweetData.media.images.filter(img => img !== null);
                    
                    // Update hasMedia flag based on what actually loaded
                    tweetData.hasMedia = tweetData.media.images.length > 0 || 
                                       tweetData.media.videos.length > 0 || 
                                       tweetData.media.gifs.length > 0;
                }
            }

            return tweetData;
        } catch (error) {
            console.error(`Error processing column ${columnIndex}:`, error);
            return null;
        }
    }

    async findNewestTweet(column) {
        try {
            const selectors = [
                'article[data-testid="tweet"]',
                'div[data-testid="cellInnerDiv"] article',
                'article'
            ];

            for (const selector of selectors) {
                const tweets = await column.findElements(By.css(selector));
                if (tweets.length > 0) {
                    const isValid = await this.driver.executeScript(`
                        const tweet = arguments[0];
                        return tweet.querySelector('time') !== null;
                    `, tweets[0]);

                    if (isValid) return tweets[0];
                }
            }

            const tweets = await this.driver.executeScript(`
                const column = arguments[0];
                const tweets = Array.from(column.querySelectorAll('article, [data-testid="tweet"]'))
                    .filter(tweet => tweet.querySelector('time'));
                return tweets;
            `, column);

            return tweets.length > 0 ? tweets[0] : null;
        } catch (error) {
            console.error('Error finding newest tweet:', error);
            return null;
        }
    }

    async extractTweetData(article) {
        if (!article) return null;

        try {
            // Extract tweet data directly
            const tweetInfo = await this.driver.executeScript(
                `const article = arguments[0];
                
                // Check for repost indicator and get original author
                const socialContext = article.parentElement?.querySelector('[data-testid="socialContext"]');
                const isRepost = socialContext?.textContent.toLowerCase().includes('reposted') || false;
                let originalAuthor = '';
                if (isRepost) {
                    // Extract the name before "reposted" (e.g., "Starknet" from "Starknet reposted")
                    const repostText = socialContext.textContent;
                    originalAuthor = repostText.split(' reposted')[0].trim();
                }
                
                // Check for quote tweet structure (only if not a repost)
                const textElements = article.querySelectorAll('[data-testid="tweetText"]');
                const userElements = article.querySelectorAll('[data-testid="User-Name"]');
                const isQuoteRetweet = !isRepost && textElements.length === 2 && userElements.length === 2;
                
                let quotedContent = null;
                let repostedContent = null;
                
                if (isQuoteRetweet) {
                    // For quote tweets, use the second text element as quoted content
                    quotedContent = {
                        text: textElements[1].textContent || '',
                        authorHandle: Array.from(userElements[1].querySelectorAll('span'))
                            .find(span => span.textContent.includes('@'))?.textContent.trim().replace(/^@/, '') || ''
                    };
                } else if (isRepost) {
                    // For reposts, use the main content as reposted content
                    repostedContent = {
                        text: textElements[0]?.textContent || '',
                        authorHandle: Array.from(userElements[0].querySelectorAll('span'))
                            .find(span => span.textContent.includes('@'))?.textContent.trim().replace(/^@/, '') || ''
                    };
                }

                // Get tweet ID using existing methods
                let tweetId = article.getAttribute('data-tweet-id');
                if (!tweetId) {
                    const timeLink = article.querySelector('time')?.parentElement;
                    if (timeLink) {
                        const href = timeLink.getAttribute('href');
                        const match = href?.match(/status\\/(\\d+)/);
                        if (match) tweetId = match[1];
                    }
                }
                
                if (!tweetId) {
                    const withId = article.querySelector('[data-tweet-id]');
                    if (withId) tweetId = withId.getAttribute('data-tweet-id');
                }

                // Get main tweet text (first text element)
                const tweetText = textElements[0]?.textContent || '';

                // Get main author info (first user element)
                const authorElement = userElements[0];
                let authorName = '';
                let authorHandle = '';
                
                if (authorElement) {
                    // Get all spans and find the one with @ for handle
                    const spans = Array.from(authorElement.querySelectorAll('span'));
                    const handleSpan = spans.find(span => span.textContent.includes('@'));
                    const nameSpan = spans.find(span => !span.textContent.includes('@') && span.textContent.trim());
                    
                    if (handleSpan) {
                        authorHandle = handleSpan.textContent.trim().replace(/^@/, '');
                    }
                    
                    if (nameSpan) {
                        authorName = nameSpan.textContent.trim();
                    }
                }

                // Get profile picture
                const pfpElement = article.querySelector('img[src*="profile_images"]');
                let profilePicture = '';
                if (pfpElement) {
                    profilePicture = pfpElement.src;
                    // Handle different Twitter profile picture URL formats
                    if (profilePicture) {
                        // Remove any query parameters first
                        profilePicture = profilePicture.split('?')[0];
                        // Replace size to get high quality version
                        profilePicture = profilePicture
                            .replace('_normal.', '.')
                            .replace('_bigger.', '.')
                            .replace('_mini.', '.')
                            .replace('_200x200.', '.')
                            .replace('_400x400.', '.');
                        // Add format if needed
                        if (!profilePicture.endsWith('.jpg') && !profilePicture.endsWith('.png')) {
                            profilePicture += '.jpg';
                        }
                    }
                }

                // Get timestamp
                const timeElement = article.querySelector('time');
                const timestamp = timeElement ? timeElement.getAttribute('datetime') : '';

                // Get tweet URL
                const tweetUrl = timeElement?.parentElement?.href || '';

                // Check for media
                const media = {
                    images: [],
                    videos: [],
                    gifs: []
                };

                // Process images
                const images = Array.from(article.querySelectorAll('img[alt="Image"]'));
                images.forEach(img => {
                    const src = img.getAttribute('src');
                    if (src && !src.includes('emoji') && !src.includes('profile')) {
                        let imageUrl = src.split('?')[0];
                        imageUrl += '?format=jpg&name=large';
                        media.images.push({
                            url: imageUrl,
                            alt: img.getAttribute('alt') || '',
                            isRetweet: false
                        });
                    }
                });

                return {
                    id: tweetId || '',
                    text: tweetText || '',
                    author: authorHandle || '',
                    authorDisplayName: authorName || '',
                    authorHandle: authorHandle || '',
                    profilePicture: profilePicture || '',
                    timestamp: timestamp || new Date().toISOString(),
                    url: tweetUrl || '',
                    isRepost: isRepost,
                    isQuoteRetweet: isQuoteRetweet,
                    quotedContent: quotedContent,
                    repostedContent: repostedContent,
                    originalAuthor: originalAuthor,
                    hasMedia: media.images.length > 0 || media.videos.length > 0 || media.gifs.length > 0,
                    media
                };`,
                article
            );

            // Validate the tweet data
            if (!tweetInfo || !tweetInfo.id || !tweetInfo.author) {
                return null; // Silently skip invalid tweets
            }

            // If tweet has no text and no media, skip it
            if (!tweetInfo.text && !tweetInfo.hasMedia) {
                return null; // Silently skip empty tweets
            }

            return tweetInfo;
        } catch (error) {
            console.error('Error extracting tweet data:', error);
            return null;
        }
    }

    async startMonitoring() {
        console.log('Starting continuous tweet monitoring...');
        
        while (true) {
            try {
                // Skip monitoring while processing summaries
                if (global.isProcessingSummary) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }
                
                await this.scrapeTweets();
                // Small delay to prevent excessive CPU usage
                await new Promise(resolve => setTimeout(resolve, 100));
            } catch (error) {
                console.error('Error during tweet monitoring:', error);
                // Brief pause on error to prevent rapid error loops
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }
    }

    async scrapeTweets() {
        try {
            await this.checkMemoryUsage();
            
            const columns = await this.findColumns();
            if (columns.length === 0) return [];

            const columnPromises = columns.map((column, index) => {
                return new Promise(async (resolve) => {
                    try {
                        const tweet = await this.processColumn(column, index);
                        if (tweet) {
                            // Update latest tweet info
                            this.updateLatestTweet(index, tweet.id, tweet.timestamp);
                            
                            // Filter media to only include retweet media
                            tweet.media.images = tweet.media.images.filter(img => img.isRetweet);
                            tweet.media.videos = tweet.media.videos.filter(vid => vid.isRetweet);
                            tweet.media.gifs = tweet.media.gifs.filter(gif => gif.isRetweet);
                            // Update hasMedia flag based on filtered media
                            tweet.hasMedia = tweet.media.images.length > 0 || 
                                           tweet.media.videos.length > 0 || 
                                           tweet.media.gifs.length > 0;
                        }
                        resolve(tweet);
                    } catch (error) {
                        console.error(`Error processing column ${index}:`, error);
                        resolve(null);
                    }
                });
            });

            const results = await Promise.all(columnPromises);
            const newTweets = results.filter(tweet => tweet !== null);

            if (newTweets.length > 0) {
                const date = new Date().toISOString().split('T')[0];
                const tweetsByColumn = {};
                
                // Group tweets by column
                for (const tweet of newTweets) {
                    const columnIndex = tweet.columnIndex.toString();
                    if (!tweetsByColumn[columnIndex]) {
                        tweetsByColumn[columnIndex] = [];
                    }
                    tweetsByColumn[columnIndex].push(tweet);
                }
                
                // Save tweets by column
                for (const [columnIndex, tweets] of Object.entries(tweetsByColumn)) {
                    await this.storageService.saveTweetsToColumn(tweets, date, parseInt(columnIndex));
                }

                // Notify about new tweets using the callback
                if (this.options.onTweetFound) {
                    for (const tweet of newTweets) {
                        try {
                            await this.options.onTweetFound(tweet);
                        } catch (error) {
                            console.error('Error in tweet notification callback:', error);
                        }
                    }
                }
            }

            return newTweets;
        } catch (error) {
            console.error('Error scraping tweets:', error);
            return [];
        }
    }

    async close() {
        try {
            if (this.driver) {
                try {
                    // Try to quit the browser gracefully
                    await this.driver.quit().catch(() => {});
                } catch (error) {
                    // Ignore connection errors during shutdown
                    if (!error.message.includes('ECONNREFUSED')) {
                        console.error('Error closing browser:', error);
                    }
                }
                this.driver = null;
            }
            this.isLoggedIn = false;
        } catch (error) {
            console.error('Error during scraper shutdown:', error);
        }
    }

    async loadLatestTweets() {
        try {
            if (existsSync(this.options.latestTweetsPath)) {
                const data = await fsPromises.readFile(this.options.latestTweetsPath, 'utf8');
                this.latestTweets = JSON.parse(data);
            }
        } catch (error) {
            console.error('Error loading latest tweets:', error);
        }
    }

    isNewTweet(columnIndex, tweetId, timestamp) {
        const key = columnIndex.toString();
        const latest = this.latestTweets[key];
        
        if (!latest) return true;
        if (latest.id === tweetId) return false;
        
        const latestTime = new Date(latest.timestamp);
        const tweetTime = new Date(timestamp);
        return tweetTime > latestTime;
    }

    updateLatestTweet(columnIndex, tweetId, timestamp) {
        const key = columnIndex.toString();
        this.latestTweets[key] = { id: tweetId, timestamp };
        this.saveLatestTweets();
    }

    async saveLatestTweets() {
        try {
            await fsPromises.writeFile(
                this.options.latestTweetsPath,
                JSON.stringify(this.latestTweets, null, 2)
            );
        } catch (error) {
            console.error('Error saving latest tweets:', error);
        }
    }

    async scrapeExistingTweets() {
        try {
            console.log('Finding columns...');
            const columns = await this.findColumns();
            if (columns.length === 0) {
                console.log('No columns found');
                return [];
            }
            console.log(`Found ${columns.length} columns`);

            const date = new Date().toISOString().split('T')[0];
            const allTweets = [];
            const tweetsByColumn = {};

            for (let columnIndex = 0; columnIndex < columns.length; columnIndex++) {
                const column = columns[columnIndex];
                const columnTweets = [];

                // Find visible tweets in the column
                const tweets = await column.findElements(By.css('article[data-testid="tweet"]'));
                console.log(`\nColumn ${columnIndex + 1}/${columns.length}: Found ${tweets.length} tweets`);

                // Process each tweet
                for (const tweet of tweets) {
                    try {
                        const tweetData = await this.extractTweetData(tweet);
                        if (tweetData && tweetData.id) {
                            tweetData.columnIndex = columnIndex;
                            
                            // Check if this is a new tweet
                            if (this.isNewTweet(columnIndex, tweetData.id, tweetData.timestamp)) {
                                // Update latest tweet info
                                this.updateLatestTweet(columnIndex, tweetData.id, tweetData.timestamp);
                                columnTweets.push(tweetData);
                                allTweets.push(tweetData);
                            }
                        }
                    } catch (error) {
                        console.error('Error extracting tweet data:', error);
                        continue;
                    }
                }

                if (columnTweets.length > 0) {
                    tweetsByColumn[columnIndex] = columnTweets;
                    // Save tweets for this column immediately
                    await this.storageService.saveTweetsToColumn(columnTweets, date, columnIndex);
                    console.log(`Saved ${columnTweets.length} tweets for column ${columnIndex}`);
                } else {
                    console.log(`No new tweets found for column ${columnIndex}`);
                }
            }

            // Save latest tweets state
            await this.saveLatestTweets();
            console.log(`Total tweets saved: ${allTweets.length}`);

            return allTweets;
        } catch (error) {
            console.error('Error scraping existing tweets:', error);
            return [];
        }
    }

    async checkMemoryUsage() {
        const now = Date.now();
        if (now - this.lastMemoryCheck >= this.memoryCheckInterval) {
            this.lastMemoryCheck = now;
            
            // Force cleanup of any lingering data structures
            this.cleanupDataStructures();
            
            // Force garbage collection if available
            if (global.gc) {
                global.gc();
            }

            // Restart browser if memory usage is high
            const memoryUsage = process.memoryUsage();
            const heapUsedMB = Math.round(memoryUsage.heapUsed / 1024 / 1024);
            const rssUsedMB = Math.round(memoryUsage.rss / 1024 / 1024);

            console.log(`Memory usage - Heap: ${heapUsedMB}MB, RSS: ${rssUsedMB}MB`);

            if (rssUsedMB > 1536) { // If using more than 1.5GB
                console.log('High memory usage detected, restarting browser...');
                await this.restartBrowser();
            }
        }
    }

    async restartBrowser() {
        try {
            console.log('Restarting browser...');
            await this.close();
            await this.initialize();
            console.log('Browser restarted successfully');
        } catch (error) {
            console.error('Error restarting browser:', error);
            throw error;
        }
    }

    // Add new method for media verification
    async verifyMediaUrl(url) {
        try {
            // First try a simple HEAD request through the browser
            const result = await this.driver.executeScript(`
                return new Promise((resolve, reject) => {
                    const controller = new AbortController();
                    const signal = controller.signal;
                    
                    // Increased timeout to 10 seconds
                    const timeoutId = setTimeout(() => {
                        controller.abort();
                        reject(new Error('Timeout'));
                    }, 10000);
                    
                    fetch(arguments[0], { 
                        method: 'HEAD',
                        signal: signal,
                        // Add cache control headers
                        headers: {
                            'Cache-Control': 'no-cache',
                            'Pragma': 'no-cache'
                        }
                    })
                    .then(response => {
                        clearTimeout(timeoutId);
                        if (response.ok) {
                            resolve(true);
                        } else {
                            reject(new Error('Invalid response'));
                        }
                    })
                    .catch(error => {
                        clearTimeout(timeoutId);
                        // If it's a RemoteError or network error, try a GET request as fallback
                        if (error.name === 'RemoteError' || error.name === 'NetworkError') {
                            fetch(arguments[0], { 
                                method: 'GET',
                                signal: signal,
                                headers: {
                                    'Cache-Control': 'no-cache',
                                    'Pragma': 'no-cache'
                                }
                            })
                            .then(response => {
                                if (response.ok) {
                                    resolve(true);
                                } else {
                                    reject(new Error('Invalid response'));
                                }
                            })
                            .catch(finalError => {
                                reject(finalError);
                            });
                        } else {
                            reject(error);
                        }
                    });
                });
            `, url);
            
            return result;
        } catch (error) {
            console.log(`Media verification failed for URL: ${url}`, error.name || 'Unknown error');
            return false;
        }
    }

    // Add method to force cleanup of data structures
    cleanupDataStructures() {
        try {
            // Force cleanup in all services
            if (this.storageService) {
                this.storageService.cleanupDataStructures();
            }
            if (this.preprocessService) {
                this.preprocessService.cleanupDataStructures();
            }
            if (this.summaryService) {
                this.summaryService.cleanupDataStructures();
            }
            console.log('Forced cleanup of data structures completed');
        } catch (error) {
            console.error('Error during forced cleanup:', error);
        }
    }
}
