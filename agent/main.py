# app.py
import streamlit as st
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
# import openai
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
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
# Import the new modules
from model_manager import ModelManager
from ticker_resolver import resolve_ticker
from financial_analyzer import generate_financial_report
from news_processor import fetch_macroeconomic_news, get_news_json, scrape_and_cache_articles
from stock_data import generate_stock_cache
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
    # openai.api_key = api_key

    try:
        # Check if model is specified and adjust max_tokens accordingly
        if model == "gpt-4o":
            # GPT-4o supports up to 128k tokens
            safe_max_tokens = min(max_tokens, 4000)  # Keep output reasonable
        elif model == "gpt-4":
            # GPT-4 supports up to 8k output tokens
            safe_max_tokens = min(max_tokens, 4000)
        elif model == "gpt-3.5-turbo":
            # GPT-3.5-turbo supports up to 4k output tokens
            safe_max_tokens = min(max_tokens, 3000)
        else:
            # Default safe value
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


def rank_articles(json_file_path, ticker, api_key, status_text, model=None):
    """Rank articles by relevance using the ModelManager"""
    status_text.text('Ranking news articles by relevance...')
    debug_log(f"Ranking articles from {json_file_path}", status_text)
    
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

    debug_log(f"Sending {len(relevant_articles)} articles to model ranking", status_text)
    
    # Initialize model manager
    from model_manager import ModelManager
    model_manager = ModelManager(api_key)
    
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

    log_network_operation("api.openai.com", "API_CALL", f"Ranking articles", size_bytes=len(prompt))
    
    try:
        response_text = model_manager.invoke_model(
            "ranking", 
            prompt,
            response_format={"type": "json_object"}
        )
        
        log_network_operation("api.openai.com", "API_RESPONSE", f"Received response for ranking", size_bytes=len(response_text))
        debug_log("Received response from model", status_text)
        
        # Parse the response
        ranking_result = json.loads(response_text)
        rankings = ranking_result.get("rankings", [])
        
        if not rankings:
            debug_log("AI returned empty rankings", status_text)
            st.warning("AI assistant returned empty rankings. This might be due to API limitations.")
            return None
            
    except json.JSONDecodeError as e:
        debug_log(f"JSON parse error: {str(e)}\nResponse: {response_text[:200]}...", status_text)
        st.warning(f"Error parsing AI response: {str(e)}. Please try again.")
        return None
    except Exception as e:
        debug_log(f"Error in model invocation: {str(e)}", status_text)
        st.error(f"Error ranking articles: {str(e)}")
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
        st.info("Using specialized AI models for different analysis tasks:")
        st.markdown("""
        - Ticker Resolution: GPT-3.5 Turbo
        - Fact Extraction: GPT-3.5 Turbo 16K
        - Article Ranking: GPT-3.5 Turbo
        - Financial Analysis: GPT-4o
        - Macroeconomic Analysis: GPT-3.5 Turbo 16K
        """)
        
        # Keep your existing model selector for compatibility, but it will only be used for old functions not using ModelManager
        ai_model = st.selectbox(
            "Legacy Model (for non-optimized tasks only)",
            options=["gpt-4o", "gpt-4", "gpt-3.5-turbo"],
            index=0,
            help="This model is only used for legacy functions that don't use the multi-model system."
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
   
    # In your submit_button handler, update the function calls:
    if submit_button:
        api_key = os.getenv("OPENAI_API_KEY")
        if not ticker:
            st.error("Please enter a ticker symbol.")
        elif not api_key:
            st.error("OpenAI API key not found. Make sure it's set in your .env file.")
        else:
            # Reset file tracker if in developer mode
            if developer_mode:
                file_tracker.clear()
                update_file_ops()
            
            # Setup progress indicators
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Debug log configuration
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
            
            debug_to_ui(f"Starting analysis for {ticker} over {n_days} days using multi-model approach")
            
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
                # Your existing developer mode code
                pass
            
            try:
                # Step 1: Fetch macroeconomic news (15%)
                status_text.text("Analyzing macroeconomic environment...")
                debug_to_ui("Starting macroeconomic news fetch")
                macro_news = fetch_macroeconomic_news(status_text, config.ECONOMY_RSS_FEEDS)
                debug_to_ui(f"Fetched macro news: {len(str(macro_news))} characters")
                progress_bar.progress(15)
                
                # Step 2: Get company news (30%)
                status_text.text(f"Collecting insights for {ticker}...")
                debug_to_ui(f"Starting news collection for {ticker}")
                news_json = get_news_json(ticker, status_text, n_days, TEMP_DIR, config.NEWS_TOKEN_FILENAME_TEMPLATE, tracked_open)
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
                # Step 3: Get stock data (40%) - continued
                debug_to_ui(f"Stock cache generated: {len(stock_cache)} characters")
                progress_bar.progress(40)
                
                # Step 4: Rank articles (50%)
                status_text.text("Prioritizing relevant information...")
                debug_to_ui(f"Starting article ranking using news file: {news_json}")

                ranked_json = rank_articles(news_json, ticker, api_key, status_text, model=None)
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
                cached_data = scrape_and_cache_articles(json_file_path=ranked_json, 
                                                    ticker=ticker, 
                                                    status_text=status_text,
                                                    max_tokens_news_scraping=config.MAX_TOKENS_NEWS_SCRAPING,
                                                    tracked_open_func=tracked_open)
                
                debug_to_ui(f"Content extracted: {len(cached_data)} characters")
                progress_bar.progress(60)
                
                # Step 6: Generate financial report (80%)
                status_text.text("Generating comprehensive financial analysis...")
                debug_to_ui("Starting financial report generation")
                financial_report = generate_financial_report(ticker=ticker, 
                                                        cached_data=cached_data, 
                                                        macro_news=macro_news, 
                                                        stock_cache=stock_cache, 
                                                        api_key=api_key, 
                                                        status_text=status_text)
                
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


