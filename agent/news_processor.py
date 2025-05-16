# news_processor.py
import requests
from bs4 import BeautifulSoup
import feedparser
import json
from datetime import datetime, timedelta
import pytz
import os
import time
import re
import tiktoken

def num_tokens_from_string(string, encoding_name="cl100k_base"):
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def extract_date(date_string):
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

def fetch_macroeconomic_news(status_text, economy_rss_feeds):
    news_cache = {}
    counter = 0

    for source_name, rss_url in economy_rss_feeds.items():
        feed = feedparser.parse(rss_url)
        source_articles = []

        for idx, entry in enumerate(feed.entries[:3], start=1):
            counter += 1
            if status_text:
                status_text.text(f"Reading macroeconomic data... {counter}")
            
            full_content = extract_news_content(entry.link)

            article_data = {
                "title": entry.title,
                "link": entry.link,
                "published": entry.published if "published" in entry else "Unknown Date",
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

def get_news_json(ticker, status_text, n_days, temp_dir, news_token_filename_template, tracked_open_func=open):
    token_data = []
    
    today = datetime.now(pytz.utc)
    threshold_date = today - timedelta(days=n_days)
    
    if status_text:
        status_text.text(f"Searching for {ticker} news from the past {n_days} days...")

    rss_urls = [
        f'https://finance.yahoo.com/rss/headline?s={ticker}',
        f'https://news.google.com/rss/search?q={ticker}+stock', 
    ]

    total_found = 0
    
    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
                
            if status_text:
                status_text.text(f"Found {len(feed.entries)} articles about {ticker}")
            total_found += len(feed.entries)

            for entry in feed.entries:
                pub_date = entry.published if "published" in entry else "No Date"
                article_datetime = extract_date(pub_date)
                
                is_in_interval = True
                if not article_datetime or article_datetime < threshold_date:
                    is_in_interval = False

                article_url = entry.link
                accessible = scrape_news(article_url)

                if status_text:
                    status_text.text(f'Discovering articles about {ticker}...')
                
                article_tokens = num_tokens_from_string(entry.title)

                token_data.append({
                    "title": entry.title,
                    "url": article_url,
                    "tokens": article_tokens,
                    "date": pub_date.strip(),
                    "rank": None,
                    "out_of_interval": 0 if is_in_interval else 1,
                    "accessible": accessible
                })
        except Exception as e:
            if status_text:
                status_text.text(f"Error fetching from {rss_url}: {str(e)}")
    
    if not token_data:
        if status_text:
            status_text.text(f"No news articles found for {ticker}. Try a different ticker or increase the date range.")
        return None
        
    if status_text:
        status_text.text(f"Processing articles for {ticker}")
    
    filename = os.path.join(temp_dir, news_token_filename_template.format(ticker=ticker))
    
    try:
        with tracked_open_func(filename, 'w', encoding='utf-8', tracker_msg=f"Writing {len(token_data)} news tokens") as json_file:
            json.dump(token_data, json_file, indent=4)
    except Exception as e:
        if status_text:
            status_text.text(f"Error writing to file {filename}: {str(e)}")
        return None
    
    return filename

def scrape_and_cache_articles(json_file_path, ticker, status_text, max_tokens_news_scraping, tracked_open_func=open):
    try:
        with tracked_open_func(json_file_path, "r", encoding="utf-8", tracker_msg="Reading ranked articles for scraping") as file:
            ranked_articles = json.load(file)
    except Exception as e:
        if status_text:
            status_text.text(f"Error reading ranked articles: {str(e)}")
        return "Error: Could not read ranked articles file"

    top_articles = sorted(ranked_articles, key=lambda x: x.get("rank", 999))[:20]
    
    cache_content = []
    scrape_counter = 0
    success_counter = 0
    total_tokens = 0
    
    for article in top_articles:
        title = article["title"]
        url = article["url"]
        scrape_counter += 1
        if status_text:
            status_text.text(f"Analyzing financial data ({scrape_counter}/{len(top_articles)})")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            # Enhanced article body selection
            article_body = soup.find("article") or \
                           soup.find("div", class_=re.compile(r'(article|content|story|post)-?(body|content|text)', re.I)) or \
                           soup.find("main")
            
            content_extracted = ""
            if article_body:
                paragraphs = article_body.find_all("p")
                content_extracted = "\n".join([p.get_text(separator=' ', strip=True) for p in paragraphs])
                
                article_tokens = num_tokens_from_string(content_extracted)
                
                if total_tokens + article_tokens > max_tokens_news_scraping:
                    break 
                
                total_tokens += article_tokens
                success_counter += 1
            else:
                content_extracted = "Could not extract content"

            article_content_formatted = f"🔹 {title}\n🔗 {url}\n\n{content_extracted}\n{'-'*80}\n"
            cache_content.append(article_content_formatted)

        except Exception as e:
            if status_text:
                status_text.text(f"Error scraping {url}: {str(e)}")
            continue

    if not cache_content:
        if status_text:
            status_text.text("Failed to extract content from any of the articles")
        return "No article content could be extracted"
    
    if status_text:
        status_text.text(f"Successfully scraped {success_counter} out of {scrape_counter} articles")
    
    return "\n".join(cache_content)