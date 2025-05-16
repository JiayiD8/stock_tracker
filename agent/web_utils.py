import requests
from bs4 import BeautifulSoup
import feedparser
import json
from datetime import datetime, timedelta
import pytz
import os
import time
import tiktoken 

import config #

def num_tokens_from_string(string, encoding_name="cl100k_base"):
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def extract_date(date_string): # Helper for get_news_json
    try:
        cleaned_date_string = date_string.replace("GMT", "+0000")
        return datetime.strptime(cleaned_date_string, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return None

def extract_news_content(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.text, "lxml")
        paragraphs = soup.find_all('p')
        content = "\n".join([para.get_text() for para in paragraphs])
        return content.strip() if content else "⚠ Unable to extract article content."
    except Exception as e:
        return f"⚠ Extraction failed: {str(e)}"

def fetch_news(status_text, economy_rss_feeds, log_network_operation_func=None): 
    news_cache = {}
    counter = 0

    for source_name, rss_url in economy_rss_feeds.items(): 
        if log_network_operation_func:
            log_network_operation_func(rss_url, "RSS_FETCH", f"Fetching macroeconomic news from {source_name}")
        feed = feedparser.parse(rss_url)
        source_articles = []

        for idx, entry in enumerate(feed.entries[:3], start=1):
            counter += 1
            if status_text: 
                status_text.text(f"Reading macroeconomic data... {counter}")
            
            if log_network_operation_func:
                 log_network_operation_func(entry.link, "SCRAPE_ATTEMPT", f"Extracting content for {entry.title[:30]}...")
            full_content = extract_news_content(entry.link) 

            article_data = {
                "title": entry.title,
                "link": entry.link,
                "published": entry.published,
                "content": full_content
            }
            source_articles.append(article_data)
            time.sleep(1) 

        news_cache[source_name] = source_articles

    return news_cache

def scrape_news(url): 
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=1) 
        if response.status_code != 200:
            return 0

        soup = BeautifulSoup(response.text, "html.parser")
        article = soup.find("article") or soup.find("div", {"class": "content"})
        return 1 if article else 0 
    except:
        return 0 

def get_news_json(ticker, status_text, n_days, temp_dir, news_token_filename_template, 
                  log_network_operation_func=None, debug_log_func=None, tracked_open_func=open):
    token_data = []
    
    today = datetime.now(pytz.utc)
    threshold_date = today - timedelta(days=n_days)
    
    if status_text: status_text.text(f"Searching for {ticker} news from the past {n_days} days...")
    if debug_log_func: debug_log_func(f"Starting news search for {ticker}", status_text)

    rss_urls = [
        f'https://finance.yahoo.com/rss/headline?s={ticker}',
        f'https://news.google.com/rss/search?q={ticker}+stock', 
    ]

    new_counter = 0
    total_found = 0
    
    for rss_url in rss_urls:
        try:
            if debug_log_func: debug_log_func(f"Fetching from {rss_url}", status_text)
            if log_network_operation_func:
                log_network_operation_func(rss_url, "RSS_FETCH", f"Fetching news feed for {ticker}")
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                if debug_log_func: debug_log_func(f"No entries found in {rss_url}", status_text)
                continue
            
            if status_text: status_text.text(f"Found {len(feed.entries)} articles about {ticker}")
            total_found += len(feed.entries)

            for entry in feed.entries:
                pub_date = entry.published if "published" in entry else "No Date"
                article_datetime = extract_date(pub_date) # Uses extract_date from this file
                
                is_in_interval = True
                if not article_datetime or article_datetime < threshold_date:
                    is_in_interval = False

                article_url = entry.link
                accessible = 0
                try:
                    if log_network_operation_func:
                        log_network_operation_func(article_url, "CHECK_ACCESS", f"Testing accessibility for article")
                    accessible = scrape_news(article_url) # Uses scrape_news from this file
                    if debug_log_func: debug_log_func(f"Article {article_url} accessible: {accessible}", status_text)
                except Exception as e:
                    if status_text: status_text.text(f"Error processing article accessibility check")
                    if debug_log_func: debug_log_func(f"Error checking accessibility for {article_url}: {e}", status_text)
                    accessible = 0

                new_counter += 1
                if status_text: status_text.text(f'Discovering articles about {ticker}...')
                
                article_tokens = num_tokens_from_string(entry.title) # Uses num_tokens_from_string

                token_data.append({
                    "title": entry.title,
                    "url": article_url,
                    "tokens": article_tokens,
                    "date": pub_date.strip(),
                    "rank": None, # Rank is added later
                    "out_of_interval": 0 if is_in_interval else 1,
                    "accessible": accessible
                })
        except Exception as e:
            if debug_log_func: debug_log_func(f"Error fetching from {rss_url}: {str(e)}", status_text)
    
    if not token_data:
        # Note: st.warning needs Streamlit context, so this logic might be better handled in main.py
        # or passed as a callback. For simplicity, returning None and main.py can show the warning.
        # if total_found > 0:
        #     print(f"Warning: Found {total_found} articles about {ticker}, but none were recent or accessible")
        # else:
        #     print(f"Warning: No news articles found for {ticker}.")
        return None
        
    if status_text: status_text.text(f"Processing articles for {ticker}")
    
    filename = os.path.join(temp_dir, news_token_filename_template.format(ticker=ticker))
    if debug_log_func: debug_log_func(f"Writing to file: {filename}", status_text)
    
    try:
        with tracked_open_func(filename, 'w', encoding='utf-8', tracker_msg=f"Writing {len(token_data)} news tokens") as json_file:
            json.dump(token_data, json_file, indent=4)
        if debug_log_func: debug_log_func(f"Successfully wrote {len(token_data)} articles to {filename}", status_text)
    except Exception as e:
        if debug_log_func: debug_log_func(f"Error writing to file {filename}: {str(e)}", status_text)
        return None
    
    return filename

def scrape_and_cache_articles(json_file_path, ticker, status_text, max_tokens_news_scraping,
                              log_network_operation_func=None, debug_log_func=None, tracked_open_func=open):
    if debug_log_func: debug_log_func(f"Scraping articles from {json_file_path}", status_text)
    
    try:
        with tracked_open_func(json_file_path, "r", encoding="utf-8", tracker_msg="Reading ranked articles for scraping") as file:
            ranked_articles = json.load(file)
        if debug_log_func: debug_log_func(f"Successfully loaded {len(ranked_articles)} ranked articles", status_text)
    except Exception as e:
        if debug_log_func: debug_log_func(f"Error reading ranked articles: {str(e)}", status_text)
        return "Error: Could not read ranked articles file"

    top_articles = sorted(ranked_articles, key=lambda x: x.get("rank", 999))[:20] # Limit to top 20
    if debug_log_func: debug_log_func(f"Selected top {len(top_articles)} articles for processing", status_text)
    
    cache_content = []
    scrape_counter = 0
    success_counter = 0
    total_tokens = 0
    
    for article in top_articles:
        title = article["title"]
        url = article["url"]
        scrape_counter += 1
        if status_text: status_text.text(f"Analyzing financial data ({scrape_counter}/{len(top_articles)})")
        if debug_log_func: debug_log_func(f"Scraping article {scrape_counter}: {url}", status_text)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            if log_network_operation_func:
                log_network_operation_func(url, "SCRAPE", f"Scraping article content: {title[:30]}...")
            
            response = requests.get(url, headers=headers, timeout=10) 
            content_size = len(response.content)

            if log_network_operation_func:
                log_network_operation_func(url, "RESPONSE", f"Received article content", status_code=response.status_code, size_bytes=content_size)

            if response.status_code != 200:
                if debug_log_func: debug_log_func(f"Article returned status code: {response.status_code}", status_text)
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            # Enhanced article body selection
            article_body = soup.find("article") or \
                           soup.find("div", class_=re.compile(r'(article|content|story|post)-?(body|content|text)', re.I)) or \
                           soup.find("main") 
            
            content_extracted_this_article = ""
            if article_body:
                paragraphs = article_body.find_all("p")
                content_extracted_this_article = "\n".join([p.get_text(separator=' ', strip=True) for p in paragraphs])
                
                article_tokens = num_tokens_from_string(content_extracted_this_article)
                
                if total_tokens + article_tokens > max_tokens_news_scraping:
                    if debug_log_func: debug_log_func(f"Token limit would be exceeded. Current: {total_tokens}, Article: {article_tokens}, Max: {max_tokens_news_scraping}", status_text)
                    break 
                
                total_tokens += article_tokens
                success_counter += 1
            else:
                if debug_log_func: debug_log_func(f"Could not find article body in {url}", status_text)
                content_extracted_this_article = "Could not extract content"

            article_content_formatted = f"🔹 {title}\n🔗 {url}\n\n{content_extracted_this_article}\n{'-'*80}\n"
            cache_content.append(article_content_formatted)
            if debug_log_func: debug_log_func(f"Article {scrape_counter} added. Total tokens now: {total_tokens}/{max_tokens_news_scraping}", status_text)

        except Exception as e:
            if debug_log_func: debug_log_func(f"Error scraping {url}: {str(e)}", status_text)
            continue

    if not cache_content:
        return "No article content could be extracted"
    
    if debug_log_func: debug_log_func(f"Successfully scraped {success_counter} out of {scrape_counter} articles. Total tokens: {total_tokens}", status_text)
    
    full_content_str = "\n".join(cache_content)
   
    return full_content_str