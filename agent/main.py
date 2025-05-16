# app.py
import streamlit as st
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
# import openai
import httpx
from openai import OpenAI
import json
import feedparser
import requests
from bs4 import BeautifulSoup
import tiktoken
import re
import pytz  
import time
import threading
import tempfile
import smtplib
from ticker_resolver import resolve_ticker
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

from ppt_generator import create_ppt, create_slide_previews, convert_ppt_to_images

import ssl
import certifi

import config

# Configure SSL to use certifi's certificate bundle
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

# Set page configuration
st.set_page_config(
    page_title=config.PAGE_CONFIG["page_title"], 
    page_icon=config.PAGE_CONFIG["page_icon"],   
    layout=config.PAGE_CONFIG["layout"]          
)

# Apply premium modern dark theme
st.markdown(config.CSS_THEME, unsafe_allow_html=True)

# Initialize session state
if 'progress' not in st.session_state:
    st.session_state.progress = 0

# Use a fixed temporary directory for file operations
TEMP_DIR = os.path.join(tempfile.gettempdir(), config.TEMP_DIR_NAME) # <<<< CHANGED
os.makedirs(TEMP_DIR, exist_ok=True)

# File operations tracking
class FileTracker:
    def __init__(self):
        self.operations = []
        self.start_time = time.time()

    def log_operation(self, operation_type, filename, details="", size_bytes=None):
        """Log a file operation with timestamp"""
        elapsed = time.time() - self.start_time
        if size_bytes is not None:
            size_info = f"{size_bytes / 1024:.2f} KB"
        else:
            size_info = "N/A"
            
        self.operations.append({
            "timestamp": f"{elapsed:.2f}s",
            "operation": operation_type,
            "file": filename,
            "details": details,
            "size": size_info
        })
    
    def get_logs(self):
        """Return logs as a DataFrame"""
        return pd.DataFrame(self.operations)
        
    def clear(self):
        """Clear all logged operations"""
        self.operations = []
        self.start_time = time.time()

# Initialize the file tracker
file_tracker = FileTracker()

def tracked_open(filepath, mode, encoding=None, tracker_msg=""):
    """Wrapper around open() that logs file operations"""
    operation = "read" if "r" in mode else "write" if "w" in mode else "append" if "a" in mode else "other"
    try:
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        file_tracker.log_operation(operation, filepath, tracker_msg, file_size)
    except Exception as e:
        file_tracker.log_operation(operation, filepath, f"Error checking file: {str(e)}")
    
    if encoding:
        return open(filepath, mode, encoding=encoding)
    else:
        return open(filepath, mode)

# Function to log network operations
def log_network_operation(url, operation_type="GET", details="", status_code=None, size_bytes=None):
    """Log a network operation"""
    status_info = f"Status: {status_code}" if status_code is not None else ""
    full_details = f"{details} {status_info}".strip()
    file_tracker.log_operation(operation_type, url, full_details, size_bytes)

# Functions from your notebook
def chatgpt_api_call(prompt, api_key, model=config.DEFAULT_OPENAI_MODEL, max_tokens=config.DEFAULT_MAX_TOKENS_CHATGPT):
    client = OpenAI(api_key=api_key)

    try:
        if model == "gpt-4o":
            safe_max_tokens = min(max_tokens, 4000)  
        elif model == "gpt-4":
            safe_max_tokens = min(max_tokens, 4000)
        elif model == "gpt-3.5-turbo":
            safe_max_tokens = min(max_tokens, 3000)
        else:
            safe_max_tokens = min(max_tokens, 2000)
            
        print(f"Using model: {model} with max_tokens: {safe_max_tokens}")
        file_tracker.log_operation("API_REQUEST", f"OpenAI/{model}", 
                                  f"Request with max_tokens={safe_max_tokens}", 
                                  len(prompt))
        
        start_time = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a financial report analyst as API agent"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=safe_max_tokens,
            temperature=0
        )
        
        response_time = time.time() - start_time
        response_text = response.choices[0].message.content.strip()
        
        file_tracker.log_operation("API_RESPONSE", f"OpenAI/{model}", 
                                  f"Response received in {response_time:.2f}s", 
                                  len(response_text))
        
        return response_text
    except Exception as e:
        error_msg = str(e)
        print(f"OpenAI API Error: {error_msg}")
        file_tracker.log_operation("API_ERROR", f"OpenAI/{model}", error_msg)
        # Return a structured error that won't cause JSON parsing issues
        return json.dumps({"error": f"API Error: {error_msg}"})

def extract_news_content(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.text, "lxml")
        paragraphs = soup.find_all('p')
        content = "\n".join([para.get_text() for para in paragraphs])
        return content.strip() if content else "⚠ Unable to extract article content."
    except Exception as e:
        return f"⚠ Extraction failed: {str(e)}"

def send_ppt_email(email, ppt_file_path, ticker, sender_email, app_password):
    """Send the PPT file to the specified email"""
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = email
        message["Subject"] = f"Stock AI: {ticker} Financial Analysis Report"
        
        # Add body text
        body = f"""
        Hello,
        
        Your {ticker} financial analysis report is attached to this email.
        
        Thank you for using Stock AI.
        """
        message.attach(MIMEText(body, "plain"))
        
        # Add attachment
        with open(ppt_file_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename= {config.PPT_FILENAME_TEMPLATE.format(ticker=ticker)}",
        )
        
        message.attach(part)
        text = message.as_string()
        
        # Connect to server and send email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, email, text)
            
        return True, "Email sent successfully!"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def fetch_news(status_text):
    news_cache = {}
    counter = 0

    for source_name, rss_url in config.ECONOMY_RSS_FEEDS.items():
        feed = feedparser.parse(rss_url)
        source_articles = []

        for idx, entry in enumerate(feed.entries[:3], start=1):
            counter += 1
            status_text.text(f"Reading macroeconomic data... {counter}")
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

def extract_date(date_string):
    try:
        cleaned_date_string = date_string.replace("GMT", "+0000")
        return datetime.strptime(cleaned_date_string, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return None

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

# Function to calculate tokens for GPT models
def num_tokens_from_string(string, encoding_name="cl100k_base"):
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def get_news_json(ticker, status_text, n_days=config.DEFAULT_N_DAYS):
    token_data = []
    
    today = datetime.now(pytz.utc)
    threshold_date = today - timedelta(days=n_days)
    
    status_text.text(f"Searching for {ticker} news from the past {n_days} days...")
    debug_log(f"Starting news search for {ticker}", status_text)

    rss_urls = [
        f'https://finance.yahoo.com/rss/headline?s={ticker}',
        f'https://news.google.com/rss/search?q={ticker}+stock', 
    ]

    new_counter = 0
    total_found = 0
    
    for rss_url in rss_urls:
        try:
            debug_log(f"Fetching from {rss_url}", status_text)
            log_network_operation(rss_url, "RSS_FETCH", f"Fetching news feed for {ticker}")
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                debug_log(f"No entries found in {rss_url}", status_text)
                continue
                
            status_text.text(f"Found {len(feed.entries)} articles about {ticker}")
            total_found += len(feed.entries)

            # Rest of your existing code for processing entries...
            for entry in feed.entries:
                pub_date = entry.published if "published" in entry else "No Date"
                article_datetime = extract_date(pub_date)
                
                # Check if article is within time interval
                is_in_interval = True
                if not article_datetime or article_datetime < threshold_date:
                    is_in_interval = False

                article_url = entry.link
                try:
                    log_network_operation(article_url, "CHECK_ACCESS", f"Testing accessibility for article")
                    accessible = scrape_news(article_url)
                    debug_log(f"Article {article_url} accessible: {accessible}", status_text)
                except Exception as e:
                    status_text.text(f"Error processing article")
                    accessible = 0

                new_counter += 1
                status_text.text(f'Discovering articles about {ticker}...')
                
                # Calculate token count
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
            debug_log(f"Error fetching from {rss_url}: {str(e)}", status_text)
    
    if not token_data:
        if total_found > 0:
            st.warning(f"Found {total_found} articles about {ticker}, but none were recent (within {n_days} days) or accessible")
        else:
            st.warning(f"No news articles found for {ticker}. Try a different ticker or increase the date range.")
        return None
        
    status_text.text(f"Processing articles for {ticker}")
    
    # Use absolute path for file operations
    filename = os.path.join(TEMP_DIR, config.NEWS_TOKEN_FILENAME_TEMPLATE.format(ticker=ticker))
    debug_log(f"Writing to file: {filename}", status_text)
    
    try:
        with tracked_open(filename, 'w', encoding='utf-8', tracker_msg=f"Writing {len(token_data)} news tokens") as json_file:
            json.dump(token_data, json_file, indent=4)
        debug_log(f"Successfully wrote {len(token_data)} articles to {filename}", status_text)
    except Exception as e:
        debug_log(f"Error writing to file {filename}: {str(e)}", status_text)
        return None
    
    return filename

def generate_stock_cache(ticker, n_days, status_text):
    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=n_days)).strftime('%Y-%m-%d')

    status_text.text(f"Fetching stock data for {ticker}...")
    stock = yf.Ticker(ticker)
    data = stock.history(start=start_date, end=end_date, interval='1d')

    if data.empty:
        return None

    data['Volatility'] = data['High'] - data['Low']
    
    stock_cache = []
    for date, row in data.iterrows():
        formatted_date = date.strftime('%m-%d-%Y')
        stock_cache.append(f"{formatted_date}: price: {row['Close']:.2f}, volatility: {row['Volatility']:.2f}, volume: {int(row['Volume'])}")

    return "\n".join(stock_cache)

def rank_articles(json_file_path, ticker, api_key, status_text, model=config.DEFAULT_OPENAI_MODEL):
    status_text.text('Ranking news articles by relevance...')
    debug_log(f"Ranking articles from {json_file_path} using model {model}", status_text)
    
    try:
        with tracked_open(json_file_path, "r", encoding="utf-8", tracker_msg="Reading news tokens for ranking") as file:
            articles = json.load(file)
        debug_log(f"Successfully loaded {len(articles)} articles from {json_file_path}", status_text)
    except Exception as e:
        debug_log(f"Error reading file {json_file_path}: {str(e)}", status_text)
        st.error(f"Error reading news file: {str(e)}")
        return None
    
    if not articles:
        st.warning(f"No news articles were found for {ticker}. Try a different ticker or increase the date range.")
        return None
    
    # Filter out articles that are out of interval or not accessible
    filtered_articles = [
        article for article in articles
        if article["out_of_interval"] == 0 and article["accessible"] == 1
    ]
    
    total_articles = len(articles)
    accessible_articles = sum(1 for article in articles if article["accessible"] == 1)
    in_interval_articles = sum(1 for article in articles if article["out_of_interval"] == 0)
    filtered_count = len(filtered_articles)
    
    status_text.text(f"Found {total_articles} articles, {accessible_articles} accessible, {in_interval_articles} within time range, {filtered_count} valid")
    debug_log(f"Article stats: total={total_articles}, accessible={accessible_articles}, in_interval={in_interval_articles}, valid={filtered_count}", status_text)
    
    if not filtered_articles:
        if total_articles > 0 and accessible_articles == 0:
            st.warning(f"Found {total_articles} articles for {ticker}, but none were accessible (possibly behind paywalls)")
        elif in_interval_articles == 0:
            st.warning(f"Found {total_articles} articles for {ticker}, but none were within the specified time range")
        else:
            st.warning(f"No relevant articles found for {ticker}. Try a more popular ticker or increase the date range.")
        return None

    # Prepare a list of relevant articles for ranking
    relevant_articles = [
        {"title": article["title"], "url": article["url"]}
        for article in filtered_articles
    ]

    debug_log(f"Sending {len(relevant_articles)} articles to OpenAI for ranking using {model}", status_text)
    prompt = f"""
    You are an AI assistant that ranks news articles based on their importance and relevance. 
    The articles are related to the stock ticker {ticker}. 
    Rank the following articles in order of priority (1 being the most important).
    
    Articles:
    {json.dumps(relevant_articles, indent=2)}
    
    Please return the ranking in a JSON format like:
    {{"rankings": [{{"title": "Article Title", "url": "Article URL", "rank": 1}}, 
                    {{"title": "Another Title", "url": "Another URL", "rank": 2}}, ...]}}
    """

    log_network_operation("api.openai.com", "API_CALL", f"Ranking articles with {model}", size_bytes=len(prompt))
    response_text = chatgpt_api_call(prompt, api_key, model=model)
    log_network_operation("api.openai.com", "API_RESPONSE", f"Received response for ranking", size_bytes=len(response_text))
    debug_log("Received response from OpenAI", status_text)
    
    # Check if response is an error message (already in JSON format)
    try:
        response_json = json.loads(response_text)
        if "error" in response_json:
            error_message = response_json["error"]
            debug_log(f"OpenAI API returned error: {error_message}", status_text)
            st.error(f"OpenAI API error: {error_message}")
            return None
    except json.JSONDecodeError:
        # Not a JSON error response, continue processing as normal
        pass
    
    # Standard JSON extraction process
    cleaned_response_text = re.sub(r"```json\n|\n```", "", response_text).strip()

    try:
        ranking_result = json.loads(cleaned_response_text)
        
        # Check if it's an error response
        if "error" in ranking_result:
            debug_log(f"Error in API response: {ranking_result['error']}", status_text)
            st.error(f"API error: {ranking_result['error']}")
            return None
            
        rankings = ranking_result.get("rankings", [])
        debug_log(f"Parsed rankings: {len(rankings)} articles ranked", status_text)
        
        if not rankings:
            debug_log("AI returned empty rankings", status_text)
            st.warning("AI assistant returned empty rankings. This might be due to API limitations.")
            return None
            
    except json.JSONDecodeError as e:
        debug_log(f"JSON parse error: {str(e)}\nResponse: {cleaned_response_text[:200]}...", status_text)
        st.warning(f"Error parsing AI response: {str(e)}. Please try again.")
        return None

    ranked_articles = []
    for ranked in rankings:
        ranked_articles.append({
            "title": ranked["title"],
            "url": ranked["url"],
            "rank": ranked["rank"]
        })

    filename = os.path.join(TEMP_DIR, config.NEWS_RANKED_FILENAME_TEMPLATE.format(ticker=ticker))
    debug_log(f"Writing ranked articles to {filename}", status_text)
    
    try:
        with tracked_open(filename, "w", encoding="utf-8", tracker_msg=f"Writing {len(ranked_articles)} ranked articles") as file:
            json.dump(ranked_articles, file, indent=4)
        debug_log(f"Successfully wrote rankings to {filename}", status_text)
    except Exception as e:
        debug_log(f"Error writing rankings file: {str(e)}", status_text)
        return None

    return filename

def scrape_and_cache_articles(json_file_path, ticker, status_text):
    debug_log(f"Scraping articles from {json_file_path}", status_text)
    
    try:
        with tracked_open(json_file_path, "r", encoding="utf-8", tracker_msg="Reading ranked articles for scraping") as file:
            ranked_articles = json.load(file)
        debug_log(f"Successfully loaded {len(ranked_articles)} ranked articles", status_text)
    except Exception as e:
        debug_log(f"Error reading ranked articles: {str(e)}", status_text)
        return "Error: Could not read ranked articles file"

    # Limit to top 20 ranked articles
    top_articles = sorted(ranked_articles, key=lambda x: x.get("rank", 999))[:20]
    debug_log(f"Selected top {len(top_articles)} articles for processing", status_text)
    
    cache_content = []
    scrape_counter = 0
    success_counter = 0
    total_tokens = 0
    MAX_TOKENS = config.MAX_TOKENS_NEWS_SCRAPING   # Set a token limit for GPT-4o
    
    for article in top_articles:
        title = article["title"]
        url = article["url"]
        scrape_counter += 1
        status_text.text(f"Analyzing financial data ({scrape_counter}/{len(top_articles)})")
        debug_log(f"Scraping article {scrape_counter}: {url}", status_text)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            log_network_operation(url, "SCRAPE", f"Scraping article content: {title[:30]}...")
            response = requests.get(url, headers=headers, timeout=10)
            content_size = len(response.content)
            log_network_operation(url, "RESPONSE", f"Received article content", status_code=response.status_code, size_bytes=content_size)

            if response.status_code != 200:
                debug_log(f"Article returned status code: {response.status_code}", status_text)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            article_body = soup.find("article") or soup.find("div", {"class": "content"}) or soup.find("div", {"class": "article-body"})
            
            if article_body:
                paragraphs = article_body.find_all("p")
                content = "\n".join([p.get_text() for p in paragraphs])
                
                # Track token count
                article_tokens = num_tokens_from_string(content)
                
                # Check if adding this article would exceed token limit
                if total_tokens + article_tokens > MAX_TOKENS:
                    debug_log(f"Token limit would be exceeded. Current: {total_tokens}, Article: {article_tokens}, Max: {MAX_TOKENS}", status_text)
                    break
                
                total_tokens += article_tokens
                success_counter += 1
            else:
                debug_log(f"Could not find article body in {url}", status_text)
                content = "Could not extract content"

            article_content = f"🔹 {title}\n🔗 {url}\n\n{content}\n{'-'*80}\n"
            cache_content.append(article_content)
            debug_log(f"Article {scrape_counter} added. Total tokens now: {total_tokens}/{MAX_TOKENS}", status_text)

        except Exception as e:
            debug_log(f"Error scraping {url}: {str(e)}", status_text)
            continue

    if not cache_content:
        st.warning("Failed to extract content from any of the articles")
        return "No article content could be extracted"
    
    debug_log(f"Successfully scraped {success_counter} out of {scrape_counter} articles. Total tokens: {total_tokens}", status_text)
    
    # Log the final content size
    full_content = "\n".join(cache_content)
    file_tracker.log_operation("CACHE", f"{ticker}_article_cache", 
                              f"Created in-memory cache of {success_counter} articles ({total_tokens} tokens)", 
                              len(full_content))
    
    return full_content

def generate_financial_report(ticker, cached_data, macro_news, stock_cache, api_key, status_text, model=config.DEFAULT_OPENAI_MODEL):
    status_text.text("Generating financial report...")
    
    # Calculate token usage for inputs
    cached_data_tokens = num_tokens_from_string(cached_data)
    macro_news_tokens = num_tokens_from_string(str(macro_news))
    stock_cache_tokens = num_tokens_from_string(stock_cache)
    
    debug_log(f"Token counts - Cached data: {cached_data_tokens}, Macro news: {macro_news_tokens}, Stock cache: {stock_cache_tokens}", status_text)
    
    # Format macro news for the prompt
    macro_prompt = f"""
    ## Prompt: You are an Economic Analyst reviewing the latest news articles. Base on the news Only Return me Below information:
    YOU Are analysting for the economic/federal reserve/president policy/ etc that impact the marcoeconomic 
    read the text that report the economic/politcal/more national wise news, more marco news.
    YOu don read the part that about a stock/companies or micro terms in term of these. I want you be an maroeconomic reporter

    ###### Reports Informations be like  ######
    # Part1.  Keys takeaways of each economic/political news article.  (ex:who do what, what is annouced. For example: "Fed Reserve announced to increase interest rate by 0.25%")
    # Part2. What is the impact of the news on the economy? (ex: "The news is expected to increase the inflation rate")
    # Part3. What is the potential implication of the news on the stock market? (ex: "The stock market is expected to rise due to the news")
    ###### Reports Informations be like ######

    ############# Here is Format of the report ###########
    1. Events(Part1) +  Impact(Part2) + Impact on Stock(Part3)
    2. Events(Part1) +  Impact(Part2) + Impact on Stock(Part3)
    3. Events(Part1) +  Impact(Part2) + Impact on Stock(Part3)
    etc... add more if necessary

    # If currently, there is no much available news, you could always return No significant economic news currently as the response.

    here is the news:
    {macro_news}"""
    
    macro_prompt_tokens = num_tokens_from_string(macro_prompt)
    debug_log(f"Macro prompt tokens: {macro_prompt_tokens}", status_text)
    
    status_text.text("Analyzing macroeconomic trends...")
    macro_report = chatgpt_api_call(macro_prompt, api_key, model=model)
    macro_response_text = re.sub(r"```json\n|\n```", "", macro_report).strip()
    macro_response_tokens = num_tokens_from_string(macro_response_text)
    debug_log(f"Macro response tokens: {macro_response_tokens}", status_text)
    
    # Financial report prompt
    status_text.text("Creating financial analysis...")
    prompt = f"""
    ## Prompt: Imagine yourself as a senior broker, analyst, and fund manager. 

    ### Here is the MacroEconomic News:
    {macro_response_text} 
    (very important, you need to read this first, and then you can read the following news)
    (all you analyst, evluation should be on the macro term / events/ policy)
    (You should analys the general trend about economy, then to stock market up/down)
    (then you start to read the news to think during this Macro/Political/Events time what ticker will behavior given the news)

    You now have the recent news information and return rate for the ticker {ticker}.

    ## Ticker and News Data:
    {cached_data}

    ## Ticker Stock Price and Volitility:
    {stock_cache}

    ## For this ticker, describe:

    You are an financial report analyst. Write a detailed financial report based on the given information.
    All your read articels are already ranked, refine, so each of they are important for the report.
    The report should be detailed and comprehensive, covering all aspects of the company's financial health and future outlook.
    You are an very casution suspicious analyst, so you don not report as you read, but you inversely think why these article talk about this way, and what is the real situation behind the scene (inversely)

    ################################# Start of the report ######################################### (you don need to write this line)

    Your output should follow the exact format below:

    Section 1: Three Key take away from all articles read  (100 - 150 words) (the three takeaways should only for the companies/micro perspective, not the Marco news perspective)
    For each takeaway, include the number(s) of the article(s) that support this insight in [brackets] at the end.
    1.#xxxx(make up an subtitle): xxxxxxx [URL of supporting article]
    2.#xxxx(make up an subtitle): xxxxxxx [URL of supporting article]
    3.#xxxx(make up an subtitle): xxxxxxx [URL of supporting article]

    Section 2: Macro Situation and Stock Prospects (200 -  250  words)
    1.# Macro Situation(this is Subtitle one):xxxxxxxxx  (This one about Investment Environment is not about the stock itself, just do an comprenhenive summarize from above MacroEconomic News)
    2.# Future Prospects(this is Subtitle two): xxxxxxxx (if price down/up why, I need an reason what cause what down / up base on the Macro news, ex: "The news is expected to increase the inflation rate" then the stock price will down) 

    Section 3: Catalyst (100 - 200 words) (the catalyst should consider the events/thing that drive the stock up and down not the Macro news and not the three takeaways)
    1.#Catalyst 1(this is Subtitle one): xxxxxxx
    2.#Catalyst 2(this is Subtitle two): xxxxxxx
    3.#so on to add more if necessary (this is Subtitle more): xxxxxxx      # Add more if necessary
    
    Section 4: Stock Price and Volatility Analysis (100 words) (reflect only on the stock price and volatility relative with the investor expectation)
    1. #Stock Price Analysis(this is Subtitle one, explain what drive the stock up and down): xxxxxxx. 
    2. #Volatility Analysis(this is Subtitle two): xxxxxxx
    3. #What They Reflect in Term of Investor(this is Subtitle three):xxxxxxx
    
    Section 5: Investment Recommendation (100 - 200 words) (be very cautious and suspicious, and give a very detailed reason why)
    1. #What Position We Should Take (this is Subtitle one): xxxxxxx
    2. #What Price Target (this is Subtitle two): xxxxxxx
    3. #Why We Should Take This Position (this is Subtitle three): xxxxxxx
    4. #What Are The Potential Risks (this is Subtitle four): xxxxxxx
    
    For each section of the report, apply this chain-of-thought process:
    1. First, list the specific evidence from news articles that supports your analysis (quotes, numbers, or specific events)
    2. Then, explain what conventional analysis would typically conclude based on this evidence
    3. Next, explain why this conventional analysis might be incomplete or misleading
    4. Finally, provide your distinctive insight that goes beyond the surface-level observation

    This will ensure your analysis is evidence-based, distinctive, and avoids generic statements that could apply to any company.

    ################################# End of the report #########################################  (you don need to write this line)
    
    You sould at the beginning highliht the most three important news/aspect, and I want details written manner. Where you dont describe the information, but every sentence you need to use casual inference to report as what/how/why. 
    No sensentence should be left without a events/reason plus the number/people 
    Note: The symbol '#' is important for late where I input this txt file to next pipeline to detect the content and title, so please keep it.
    Note: The subtitle is important for the next pipeline to detect the content and title, so keep it in same upper case lower case as I define.
    """
    
    prompt_tokens = num_tokens_from_string(prompt)
    total_tokens = prompt_tokens + macro_response_tokens
    debug_log(f"Financial report prompt tokens: {prompt_tokens}, Total tokens so far: {total_tokens}", status_text)
    
    # Check if total tokens are within limits for model
    max_model_tokens = 128000 if model == "gpt-4o" else 16000 if model == "gpt-4" else 4000
    available_tokens = max_model_tokens - total_tokens
    
    status_text.text(f"Using {model} with {total_tokens} tokens for input and {available_tokens} available for output")
    
    financial_report = chatgpt_api_call(prompt, api_key, model=model, max_tokens=min(4000, available_tokens))
    report_tokens = num_tokens_from_string(financial_report)
    debug_log(f"Financial report output tokens: {report_tokens}, Total process tokens: {total_tokens + report_tokens}", status_text)
    
    return financial_report

def display_slides(slides, financial_report, ticker):
    """Display slide content directly in the Streamlit UI with full content from the report"""
    
    # Split into report sections
    sections = re.split(r'Section \d+: ', financial_report)[1:]
    
    # Add some extra styling for better readability - using website theme colors
    st.markdown("""
    <style>
        .slide-container {
            background-color: var(--background-secondary, #f0f2f6); /* Light background */
            border: 1px solid var(--border-color, #d1d5db);
            border-radius: var(--corner-radius, 6px);
            padding: 30px;
            margin-bottom: 40px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .slide-title {
            color: var(--text-primary, #1f2937);
            font-size: 28px;
            font-weight: bold;
            text-align: center;
            margin-bottom: 25px;
            border-bottom: 1px solid var(--border-color, #d1d5db);
            padding-bottom: 15px;
        }
        .slide-content {
            color: var(--text-secondary, #4b5563);
            font-size: 16px;
            line-height: 1.7;
        }
        .slide-subtitle {
            color: var(--text-primary, #1f2937);
            font-size: 20px;
            font-weight: bold;
            margin-top: 18px;
            margin-bottom: 12px;
            border-left: 4px solid var(--accent-color, #3b82f6);
            padding-left: 10px;
        }
        .takeaway-point {
            background-color: var(--highlight-color, #dbeafe); /* Light blue highlight */
            padding: 15px;
            border-radius: var(--corner-radius, 6px);
            margin-bottom: 15px;
            border-left: 3px solid var(--accent-color, #3b82f6);
            color: var(--text-secondary, #4b5563);
        }
        .cover-slide-ticker {
            text-align: center;
            font-size: 62px;
            font-weight: bold;
            margin: 60px 0;
            color: var(--accent-color, #3b82f6); /* Blue accent color */
        }
        .cover-slide-subtitle {
            text-align: center;
            font-size: 26px;
            color: var(--text-tertiary, #6b7280);
            margin-bottom: 40px;
        }
        .recommendation-highlight {
            background-color: var(--highlight-color, #dbeafe); /* Light blue highlight */
            border-left: 4px solid var(--accent-color, #3b82f6);
            padding: 15px;
            margin: 15px 0;
            border-radius: var(--corner-radius, 5px);
            font-weight: bold;
            color: var(--text-primary, #1f2937);
        }
        
        /* Special styling for certain slides */
        .macro-slide, .catalyst-slide, .recommendation-slide {
            background: linear-gradient(to bottom, var(--background-secondary, #f0f2f6) 0%, var(--background-tertiary, #e9ecef) 100%);
        }
        
        /* Icons for sections */
        .icon {
            font-size: 24px;
            margin-right: 10px;
            vertical-align: middle;
            color: var(--accent-color, #3b82f6);
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 style='color:var(--text-primary, #1f2937); text-align:center; margin-bottom:30px; font-size:32px;'>📊 Financial Analysis Presentation</h2>", unsafe_allow_html=True)

    # Slide 1: Cover
    st.markdown("<div class='slide-container'>", unsafe_allow_html=True)
    st.markdown("<div class='slide-title'>Stock AI Report</div>", unsafe_allow_html=True)
    st.markdown("<div class='cover-slide-subtitle'>AI-Powered Financial Analysis</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='cover-slide-ticker'>{ticker}</div>", unsafe_allow_html=True)
    st.markdown("<hr style='border-top: 2px solid #3b82f6; width: 50%; margin: 0 auto;'>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Slide 2: Three Key Takeaways
    if len(sections) > 0:
        three_key_takeaways = sections[0].strip()
        st.markdown("<div class='slide-container'>", unsafe_allow_html=True)
        st.markdown("<div class='slide-title'>⚠️ Three Key Takeaways</div>", unsafe_allow_html=True)
        
        # Extract takeaways with titles
        takeaways = re.findall(r"\d+\.\s*#(.*?)(?=\n\d+\.\s*#|\Z)", three_key_takeaways, re.DOTALL)
        
        st.markdown("<div class='slide-content'>", unsafe_allow_html=True)
        for takeaway in takeaways:
            # NEW ADDED
            # Extract URL if present
            url_match = re.search(r'\[(https?://[^\]]+)\]', takeaway)
            url = url_match.group(1) if url_match else None
            
            # Clean takeaway text
            takeaway_clean = re.sub(r'\[https?://[^\]]+\]', '', takeaway).strip()
            
            # Process takeaway
            parts = takeaway_clean.split(":", 1)
            if len(parts) == 2:
                title_part = parts[0].strip()
                # Extract just the title text after the #
                title = re.sub(r'^\d+\.\s*#', '', title_part)
                content = parts[1].strip()
                
                st.markdown(f"<div class='slide-subtitle'>📌 {title}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='takeaway-point'>{content}</div>", unsafe_allow_html=True)
                
                # Add source link if available
                if url:
                    st.markdown(f"<div style='text-align:right; font-size:0.8em; font-style:italic; margin-top:-10px; margin-bottom:15px;'><a href='{url}' target='_blank'>Source</a></div>", unsafe_allow_html=True)
        
            # parts = takeaway.split(":", 1)
            # if len(parts) == 2:
            #     title, content = parts
            #     st.markdown(f"<div class='slide-subtitle'>📌 {title.strip()}</div>", unsafe_allow_html=True)
            #     st.markdown(f"<div class='takeaway-point'>{content.strip()}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Slide 3: Macro Situation and Stock Prospects
    if len(sections) > 1:
        situation_prospects = sections[1].strip()
        st.markdown("<div class='slide-container macro-slide'>", unsafe_allow_html=True)
        st.markdown("<div class='slide-title'>📊 Investment Environment and Future Prospects</div>", unsafe_allow_html=True)
        
        # Extract financial situation parts
        situation_parts = re.findall(r"\d+\.\s*#(.*?)(?=\n\d+\.\s*#|\Z)", situation_prospects, re.DOTALL)
        
        st.markdown("<div class='slide-content'>", unsafe_allow_html=True)
        for part in situation_parts:
            parts = part.split(":", 1)
            if len(parts) == 2:
                title, content = parts
                st.markdown(f"<div class='slide-subtitle'>📈 {title.strip()}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='takeaway-point'>{content.strip()}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Slide 4: Catalysts
    if len(sections) > 2:
        catalysts = sections[2].strip()
        st.markdown("<div class='slide-container catalyst-slide'>", unsafe_allow_html=True)
        st.markdown("<div class='slide-title'>⏳ Catalyst Factors</div>", unsafe_allow_html=True)
        
        # Extract catalyst parts
        catalyst_parts = re.findall(r"\d+\.\s*#(.*?)(?=\n\d+\.\s*#|\Z)", catalysts, re.DOTALL)
        
        st.markdown("<div class='slide-content'>", unsafe_allow_html=True)
        for part in catalyst_parts:
            parts = part.split(":", 1)
            if len(parts) == 2:
                title, content = parts
                st.markdown(f"<div class='slide-subtitle'>🔍 {title.strip()}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='takeaway-point'>{content.strip()}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Slide 5: Stock Price & Volatility Analysis
    if len(sections) > 3:
        price_analysis = sections[3].strip()
        st.markdown("<div class='slide-container'>", unsafe_allow_html=True)
        st.markdown("<div class='slide-title'>📈 Stock Price & Volatility Analysis</div>", unsafe_allow_html=True)
        
        # Extract price analysis parts
        price_parts = re.findall(r"\d+\.\s*#(.*?)(?=\n\d+\.\s*#|\Z)", price_analysis, re.DOTALL)
        
        st.markdown("<div class='slide-content'>", unsafe_allow_html=True)
        for part in price_parts:
            parts = part.split(":", 1)
            if len(parts) == 2:
                title, content = parts
                st.markdown(f"<div class='slide-subtitle'>📊 {title.strip()}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='takeaway-point'>{content.strip()}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Slide 6: Investment Recommendation
    if len(sections) > 4:
        recommendation = sections[4].strip()
        st.markdown("<div class='slide-container recommendation-slide'>", unsafe_allow_html=True)
        st.markdown("<div class='slide-title'>💰 Investment Recommendation</div>", unsafe_allow_html=True)
        
        # Extract recommendation parts
        recommendation_parts = re.findall(r"\d+\.\s*#(.*?)(?=\n\d+\.\s*#|\Z)", recommendation, re.DOTALL)
        
        st.markdown("<div class='slide-content'>", unsafe_allow_html=True)
        for part in recommendation_parts:
            parts = part.split(":", 1)
            if len(parts) == 2:
                title, content = parts
                icon = "🎯" if "Position" in title else "💲" if "Price Target" in title else "⚖️" if "Why" in title else "⚠️" if "Risk" in title else "📝"
                st.markdown(f"<div class='slide-subtitle'>{icon} {title.strip()}</div>", unsafe_allow_html=True)
                
                # Highlight important points in recommendation
                if "Position" in title or "Price Target" in title:
                    st.markdown(f"<div class='recommendation-highlight'>{content.strip()}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='takeaway-point'>{content.strip()}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    # Display original slide images in expander
    with st.expander("View Slide Thumbnails", expanded=False):
        # Display slides in rows of 3
        cols_per_row = 3
        for i in range(0, len(slides), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i+j < len(slides):
                    cols[j].image(slides[i+j], caption=f"Slide {i+j+1}", use_column_width=True)
                    
def debug_log(message, status_text=None):
    """Log debug messages to both console and status text if provided"""
    print(f"DEBUG: {message}")
    if status_text:
        status_text.text(f"DEBUG: {message}")

# Initialize session state for email settings
if 'email_credentials_saved' not in st.session_state:
    st.session_state.email_credentials_saved = False
if 'sender_email' not in st.session_state:
    st.session_state.sender_email = ""
if 'app_password' not in st.session_state:
    st.session_state.app_password = ""

def save_email_credentials(email, password):
    """Save email credentials to session state"""
    st.session_state.sender_email = email
    st.session_state.app_password = password
    st.session_state.email_credentials_saved = True
    return True

def main():
    st.title("STOCK AI")
    
    # Introduction
    st.markdown("""
    ### STOCK TRACKER
    Welcome to the Stock Tracker! This tool is designed to help you analyze stock market trends and make informed investment decisions.
    """)
    
    # Debug and developer modes
    debug_mode = st.sidebar.checkbox("Enable Debug Mode", value=False)
    developer_mode = st.sidebar.checkbox("Enable Developer Mode", value=False, 
                                        help="Shows detailed file operations and network activity")
    
    # Remove the email setup section in sidebar since we're removing email delivery
    
    # If developer mode is enabled, show the file operations table
    if developer_mode:
        file_tracker.clear()  # Reset the tracker when starting a new run
        dev_tabs = st.sidebar.tabs(["File Operations", "Settings"])
        
        with dev_tabs[0]:
            st.sidebar.subheader("File & Network Operations")
            file_ops_container = st.sidebar.container()
            file_ops_placeholder = file_ops_container.empty()
            
            # Function to update the file operations display
            def update_file_ops():
                if file_tracker.operations:
                    df = file_tracker.get_logs()
                    file_ops_placeholder.dataframe(df, use_container_width=True)
                else:
                    file_ops_placeholder.info("No file operations logged yet")
            
            # Start a background thread to update the display
            def file_ops_updater():
                while True:
                    update_file_ops()
                    time.sleep(2)  # Update every 2 seconds
            
            if st.sidebar.button("Start File Tracking"):
                threading.Thread(target=file_ops_updater, daemon=True).start()
    
    # Advanced settings
    with st.sidebar.expander("Advanced Settings", expanded=False):
        ai_model = st.selectbox(
            "OpenAI Model",
            options=["gpt-4o", "gpt-4", "gpt-3.5-turbo"],
            index=0,
            help="Select which AI model to use. GPT-4o is most capable but may cost more."
        )
    # NEW ADDED
    # Add ticker resolver section before the main analysis form (around line 1020)
    # Initialize session state for ticker input
    if 'validated_ticker' not in st.session_state:
        st.session_state.validated_ticker = None

    # Only show the ticker validation UI if we don't have a validated ticker yet
    if not st.session_state.validated_ticker:
        st.title("STOCK AI")
        
        st.markdown("""
        ### STOCK TRACKER
        Welcome to the Stock Tracker! This tool is designed to help you analyze stock market trends and make informed investment decisions.
        """)
        
        # Ticker resolution section
        ticker_col1, ticker_col2 = st.columns([3, 1])
        
        with ticker_col1:
            ticker_input = st.text_input(
                "Enter stock ticker symbol or company name:",
                help="Example: AAPL, Microsoft, NVDIA (misspelling will be detected)"
            )
        
        with ticker_col2:
            check_ticker_button = st.button("Check Ticker", key="check_ticker")
        
        # Check if user has entered a ticker and clicked the button
        if check_ticker_button and ticker_input:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                st.error("OpenAI API key not found. Make sure it's set in your .env file.")
            else:
                with st.spinner("Verifying ticker symbol..."):
                    from ticker_resolver import resolve_ticker
                    result = resolve_ticker(ticker_input, api_key)
                    
                if result.get("verified") and result.get("best_match"):
                    st.success(f"✅ Valid ticker: {result['best_match']} - {result['company_name']}")
                    st.session_state.validated_ticker = result['best_match']
                    st.experimental_rerun()  # Rerun to show the analysis form
                else:
                    st.error(f"'{ticker_input}' doesn't appear to be a valid ticker symbol.")
                    
                    if result.get("best_match") and result.get("confidence", 0) > 70:
                        st.info(f"Did you mean **{result['best_match']}** ({result.get('company_name', '')})? ")
                        if st.button(f"Use {result['best_match']} instead"):
                            st.session_state.validated_ticker = result['best_match']
                            st.experimental_rerun()
                    
                    if result.get("alternatives"):
                        st.write("Or did you mean one of these?")
                        alt_cols = st.columns(min(3, len(result["alternatives"])))
                        
                        for i, alt in enumerate(result["alternatives"]):
                            if i < len(alt_cols):
                                with alt_cols[i]:
                                    if st.button(f"{alt['ticker']} - {alt.get('name', alt['ticker'])}"):
                                        st.session_state.validated_ticker = alt['ticker']
                                        st.experimental_rerun()
                    
                    st.info("Please enter a valid ticker symbol like AAPL, MSFT, GOOGL, etc.")

    # Only show main title and analysis form when we have a validated ticker
    else:
        st.title("STOCK AI - Analysis")
        st.write(f"Analyzing: **{st.session_state.validated_ticker}**")
        
        # Add a button to change ticker if needed
        if st.button("Change Ticker"):
            st.session_state.validated_ticker = None
            st.experimental_rerun()

    # Main analysis form - REMOVE delivery options
    with st.form("analysis_form"):
        # If we have a validated ticker, use it; otherwise, ask for input as before
        if st.session_state.validated_ticker:
            ticker = st.session_state.validated_ticker
            st.write(f"Stock ticker: **{ticker}**")
        else:
            ticker = st.text_input("Enter stock ticker symbol (e.g., AAPL, MSFT, TSLA):")
        
        n_days = st.slider("Number of days to analyze:", 1, 30, 7)
        
        submit_button = st.form_submit_button("Generate Analysis")
    # # Main analysis form - REMOVE delivery options
    # with st.form("analysis_form"):
    #     ticker = st.text_input("Enter stock ticker symbol (e.g., AAPL, MSFT, TSLA):")
    #     n_days = st.slider("Number of days to analyze:", 1, 30, 7)
        
    #     submit_button = st.form_submit_button("Generate Analysis")
    
    if submit_button:
        api_key = os.getenv("OPENAI_API_KEY")
        if not ticker:
            st.error("Please enter a ticker symbol.")
        elif not api_key:
            st.error("OpenAI API key not found. Make sure it's set in your .env file.")
        else:
            # Reset file tracker
            if developer_mode:
                file_tracker.clear()
                update_file_ops()
            
            # Setup progress indicators
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Debug log area if debug mode is enabled
            if debug_mode:
                debug_area = st.expander("Debug Logs", expanded=True)
                debug_container = debug_area.container()
                debug_text = debug_container.empty()
                def debug_to_ui(message):
                    current = debug_text.text or ""
                    debug_text.text(f"{current}\n{message}")
                    print(f"DEBUG: {message}")
            else:
                def debug_to_ui(message):
                    print(f"DEBUG: {message}")
            
            debug_to_ui(f"Starting analysis for {ticker} over {n_days} days using {ai_model}")
            
            # Clean up any existing files for this ticker
            try:
                for filename in os.listdir(TEMP_DIR):
                    if filename.startswith(ticker):
                        os.remove(os.path.join(TEMP_DIR, filename))
                        debug_to_ui(f"Removed old file: {filename}")
            except Exception as e:
                debug_to_ui(f"Error cleaning up files: {str(e)}")
                
            # If developer mode is enabled, show file operations in real-time
            if developer_mode:
                dev_expander = st.expander("Developer Data", expanded=True)
                
                with dev_expander:
                    dev_tabs = st.tabs(["File Operations", "Stats"])
                    
                    with dev_tabs[0]:
                        file_ops_view = st.empty()
                        
                        # Function to update the data table in the main view
                        def update_dev_view():
                            df = file_tracker.get_logs()
                            if not df.empty:
                                file_ops_view.dataframe(df, use_container_width=True)
                            else:
                                file_ops_view.info("No operations logged yet")
                    
                    with dev_tabs[1]:
                        stats_view = st.empty()
                        
                        def update_stats_view():
                            if file_tracker.operations:
                                df = file_tracker.get_logs()
                                op_counts = df['operation'].value_counts()
                                stats_view.bar_chart(op_counts)
                            else:
                                stats_view.info("No data to display yet")
                
                # Start a background thread to update both views
                def dev_view_updater():
                    while True:
                        update_dev_view()
                        update_stats_view()
                        time.sleep(1)  # Update every second
                
                threading.Thread(target=dev_view_updater, daemon=True).start()
            
            try:
                # Step 1: Fetch macroeconomic news (15%)
                status_text.text("Analyzing macroeconomic environment...")
                debug_to_ui("Starting macroeconomic news fetch")
                macro_news = fetch_news(status_text)
                debug_to_ui(f"Fetched macro news: {len(str(macro_news))} characters")
                progress_bar.progress(15)
                
                # Step 2: Get company news (30%)
                status_text.text(f"Collecting insights for {ticker}...")
                debug_to_ui(f"Starting news collection for {ticker}")
                news_json = get_news_json(ticker, status_text, n_days)
                if news_json is None:
                    st.error(f"Failed to retrieve sufficient data for {ticker}. Unable to proceed with analysis.")
                    debug_to_ui("News JSON retrieval failed")
                    return
                debug_to_ui(f"News JSON saved to: {news_json}")
                progress_bar.progress(30)
                
                # Step 3: Get stock data (40%)
                status_text.text(f"Processing market data for {ticker}...")
                debug_to_ui(f"Starting stock data retrieval for {ticker}")
                stock_cache = generate_stock_cache(ticker, n_days, status_text)
                if stock_cache is None:
                    st.error(f"No stock data found for {ticker}. Unable to proceed with analysis.")
                    debug_to_ui("Stock cache generation failed")
                    return
                debug_to_ui(f"Stock cache generated: {len(stock_cache)} characters")
                progress_bar.progress(40)
                
                # Step 4: Rank articles (50%)
                status_text.text("Prioritizing relevant information...")
                debug_to_ui(f"Starting article ranking using news file: {news_json}")
                ranked_json = rank_articles(news_json, ticker, api_key, status_text, model=ai_model)
                progress_bar.progress(50)
                
                # Check if we have ranked articles before proceeding
                if ranked_json is None:
                    st.error("Insufficient relevant data found. Unable to proceed with analysis.")
                    debug_to_ui("Article ranking failed - no ranked_json returned")
                    return
                debug_to_ui(f"Articles ranked and saved to: {ranked_json}")
                
                # Step 5: Scrape article content (60%)
                status_text.text("Extracting financial insights...")
                debug_to_ui(f"Starting content extraction from file: {ranked_json}")
                cached_data = scrape_and_cache_articles(ranked_json, ticker, status_text)
                debug_to_ui(f"Content extracted: {len(cached_data)} characters")
                progress_bar.progress(60)
                
                # Step 6: Generate financial report (80%)
                status_text.text("Generating comprehensive financial analysis...")
                debug_to_ui("Starting financial report generation")
                financial_report = generate_financial_report(ticker, cached_data, macro_news, stock_cache, api_key, status_text, model=ai_model)
                debug_to_ui(f"Financial report generated: {len(financial_report)} characters")
                progress_bar.progress(80)
                
                # Step 7: Create PowerPoint presentation (100%)
                status_text.text("Creating PowerPoint presentation...")
                debug_to_ui("Starting PowerPoint creation")
                ppt_file = create_ppt(ticker, financial_report, status_text)
                debug_to_ui(f"PowerPoint saved to: {ppt_file}")
                progress_bar.progress(100)
                
                # Show completion message
                st.success(f"✅ Analysis of {ticker} completed successfully!")
                
                # Generate slide previews
                status_text.text("Generating slide previews...")
                slide_images = create_slide_previews(ticker, financial_report)
                
                # Display slide previews
                if slide_images:
                    display_slides(slide_images, financial_report, ticker)
                
                # Download section with premium styling
                st.markdown("""
                <div style="background-color: var(--background-secondary, #f0f2f6); padding: 24px; border-radius: var(--corner-radius, 6px); margin: 24px 0; border: 1px solid var(--border-color, #d1d5db);">
                    <h3 style="color: var(--text-primary, #1f2937); margin-top: 0; font-weight: 600; letter-spacing: -0.01em;">Download Your Report</h3>
                    <p style="color: var(--text-secondary, #4b5563); font-weight: 400; letter-spacing: 0.01em;">Your financial analysis is ready to download as a PowerPoint presentation.</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Display download button
                with open(ppt_file, "rb") as file:
                    ppt_data = file.read()
                    col1, col2, col3 = st.columns([2,3,2])
                    with col2:
                        st.download_button(
                            label=f"Download {ticker} Financial Analysis PowerPoint",
                            data=ppt_data,
                            file_name=f"{ticker}_financial_report.pptx",
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            key="download_ppt"
                        )
                
                # Clean up temporary files only if not in debug mode
                if not debug_mode:
                    try:
                        for filename in [news_json, ranked_json]:
                            if filename and os.path.exists(filename):
                                os.remove(filename)
                                debug_to_ui(f"Removed temp file: {filename}")
                    except Exception as e:
                        debug_to_ui(f"Error cleaning up files: {str(e)}")
                else:
                    debug_to_ui(f"Debug mode - keeping temporary files")
            
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                status_text.text(f"Error: {str(e)}")
                debug_to_ui(f"ERROR: {str(e)}")
                import traceback
                debug_to_ui(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()

    ### This is how you should run 
    ### 1). exit()
    ### 2). streamlit run /Users/xikinki/Desktop/Stock/app.py


