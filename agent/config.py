# config.py

import os
from dotenv import load_dotenv
load_dotenv() 

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TEMP_DIR_NAME = "finance_ai_temp" 

ECONOMY_RSS_FEEDS = {
    "Yahoo Finance - Economy": "https://www.yahoo.com/news/rss/economy",
    "Google News - Federal Reserve": "https://news.google.com/rss/search?q=Federal+Reserve&hl=en-US&gl=US&ceid=US:en",
    "Google News - Inflation": "https://news.google.com/rss/search?q=inflation&hl=en-US&gl=US&ceid=US:en",
    "CNBC Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html"
}

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_MAX_TOKENS_CHATGPT = 4000 # Default for chatgpt_api_call
MAX_TOKENS_NEWS_SCRAPING = 8000 # Token limit for GPT-4o in scrape_and_cache_articles

# --- Analysis Defaults ---
DEFAULT_N_DAYS = 7

# --- Streamlit Page Configuration ---
PAGE_CONFIG = {
    "page_title": "STOCK AI",
    "page_icon": "☕",
    "layout": "wide"
}

# --- CSS Styles ---
# It's often better to put extensive CSS in a separate .css file and load it.
# However, for direct config, you can keep it here.
CSS_THEME = """
<style>
    /* Global theme - Light */
    :root {
        --background-primary: #ffffff;
        --background-secondary: #f0f2f6;
        --background-tertiary: #e9ecef;
        --border-color: #d1d5db;
        --text-primary: #1f2937;
        --text-secondary: #4b5563;
        --text-tertiary: #6b7280;
        --accent-color: #3b82f6; /* Blue accent */
        --highlight-color: #dbeafe; /* Light blue highlight */
        --button-text-color: #ffffff; /* White text for buttons with accent background */
        --button-background-color: var(--accent-color);
        --button-hover-background-color: #2563eb; /* Darker blue for hover */
        --input-background-color: #ffffff;
        --input-border-color: var(--border-color);
        --input-text-color: var(--text-primary);
        --spacing-unit: 12px;
        --corner-radius: 6px;
    }
    
    /* Base elements */
    .main {
        background-color: var(--background-primary);
        color: var(--text-primary);
        font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    }
    
    .stApp {
        background-color: var(--background-primary); 
    }
    
    /* Typography - Light Styling */
    h1 {
        color: var(--text-primary) !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        font-size: 2.5rem !important;
        margin-bottom: var(--spacing-unit) !important;
    }
    
    h2, h3 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
    }
    
    p, li, span, label, div {
        color: var(--text-secondary) !important;
        font-weight: 400 !important;
        letter-spacing: 0.01em !important;
        line-height: 1.6 !important;
    }
    
    a {
        color: var(--accent-color) !important;
        text-decoration: none !important;
        border-bottom: 1px solid var(--accent-color) !important;
    }
    
    /* Improved button styling */
    .stButton>button {
        background-color: var(--button-background-color) !important;
        color: var(--button-text-color) !important;
        border: 1px solid var(--button-background-color) !important;
        padding: 12px 24px !important;
        border-radius: var(--corner-radius) !important;
        font-weight: 500 !important;
        transition: all 0.2s ease;
        letter-spacing: 0.02em !important;
        text-transform: uppercase !important;
        font-size: 0.85rem !important;
    }
    
    .stButton>button:hover {
        background-color: var(--button-hover-background-color) !important;
        border-color: var(--button-hover-background-color) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1) !important;
    }
    
    .stButton>button:active {
        transform: translateY(0px) !important;
    }
    
    /* Download button styling */
    [data-testid="stDownloadButton"] button {
        background-color: var(--background-tertiary) !important; /* Light gray background */
        border: 1px solid var(--border-color) !important; /* Standard border */
        color: var(--text-primary) !important; /* Dark text */
        transition: all 0.3s ease !important;
    }
    
    [data-testid="stDownloadButton"] button:hover {
        background-color: var(--highlight-color) !important; /* Light blue highlight on hover */
        border-color: var(--accent-color) !important; /* Accent color border on hover */
        color: var(--accent-color) !important; /* Accent color text on hover */
    }
    
    /* Form elements */
    input, select, textarea {
        background-color: var(--input-background-color) !important;
        color: var(--input-text-color) !important;
        border: 1px solid var(--input-border-color) !important;
        border-radius: var(--corner-radius) !important;
    }
    
    .stTextInput>div>div>input {
        background-color: var(--input-background-color) !important;
        color: var(--input-text-color) !important;
        border: 1px solid var(--input-border-color) !important;
        padding: 12px 16px !important;
        border-radius: var(--corner-radius) !important;
        height: auto !important;
    }
    
    .stTextInput label, .stSelectbox label, .stSlider label {
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em !important;
        margin-bottom: 6px !important;
    }
    
    /* Selection box specific styling */
    .stSelectbox>div>div>select {
        background-color: var(--input-background-color) !important;
        color: var(--input-text-color) !important;
        border: 1px solid var(--input-border-color) !important;
        padding: 12px 16px !important;
        border-radius: var(--corner-radius) !important;
        height: auto !important;
    }
     .stSelectbox>div>div>select:focus { /* Style for when the select box is focused */
        border-color: var(--accent-color) !important;
        box-shadow: 0 0 0 0.2rem var(--highlight-color) !important;
    }

    /* Container elements */
    [data-testid="stForm"] {
        background-color: var(--background-secondary);
        border: 1px solid var(--border-color);
        border-radius: var(--corner-radius);
        padding: var(--spacing-unit);
    }
    
    /* Sidebar - Light Theme */
    [data-testid="stSidebar"] {
        background-color: var(--background-secondary) !important;
        border-right: 1px solid var(--border-color) !important;
    }
    
    [data-testid="stSidebar"] .stCheckbox label p {
        color: var(--text-secondary) !important;
    }
    
    [data-testid="stSidebar"] .stMarkdown p {
        color: var(--text-secondary) !important;
    }
    
    [data-testid="stSidebar"] h3 {
        color: var(--text-primary) !important;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 10px;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
    }
    
    /* Sidebar button styling (can be different from main content buttons if desired) */
    [data-testid="stSidebar"] .stButton button {
        background-color: var(--background-tertiary) !important; /* Slightly different background for sidebar buttons */
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
    }
     [data-testid="stSidebar"] .stButton button:hover {
        background-color: var(--highlight-color) !important;
        border-color: var(--accent-color) !important;
    }
    
    [data-testid="stSidebar"] .stExpander {
        background-color: var(--background-tertiary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--corner-radius) !important;
    }
    
    /* Developer mode panels */
    [data-testid="stSidebar"] .dataframe {
        background-color: var(--background-tertiary) !important;
        color: var(--text-primary) !important; 
    }
    
    [data-testid="stSidebar"] .dataframe th {
        background-color: #e9ecef !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        padding: 8px !important;
    }
    
    [data-testid="stSidebar"] .dataframe td {
        background-color: var(--background-tertiary) !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--border-color) !important;
        padding: 8px !important;
    }
    
    /* Alerts and messages */
    .element-container div[data-testid="stAlert"] {
        background-color: var(--highlight-color) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--accent-color) !important;
        border-left-width: 4px !important; 
        border-radius: var(--corner-radius) !important;
    }
    
    /* Containers and cards */
    .slide-container {
        background-color: var(--background-secondary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--corner-radius) !important;
        padding: 24px !important;
        margin-bottom: 24px !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
    }
    
    .slide-title {
        color: var(--text-primary) !important;
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
        margin-bottom: 16px !important;
        border-bottom: 1px solid var(--border-color) !important;
        padding-bottom: 12px !important;
    }
    
    .slide-subtitle {
        color: var(--text-primary) !important;
        font-size: 1.2rem !important;
        font-weight: 500 !important;
        margin-top: 16px !important;
        margin-bottom: 8px !important;
        border-left: 3px solid var(--accent-color) !important;
        padding-left: 10px !important;
    }
    
    .takeaway-point {
        background-color: var(--highlight-color) !important;
        border-radius: var(--corner-radius) !important;
        padding: 16px !important;
        margin-bottom: 16px !important;
        border-left: 2px solid var(--accent-color) !important;
        color: var(--text-secondary) !important;
    }
    
    /* Progress bar */
    .stProgress > div > div > div > div {
        background-color: var(--accent-color) !important;
    }
    
    /* Expander */
    .st-expander {
        background-color: var(--background-tertiary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--corner-radius) !important;
        padding: 12px !important;
    }
    
    .st-expander summary {
        font-weight: 500 !important;
        color: var(--text-primary) !important;
        letter-spacing: 0.01em !important;
    }
    
    /* Custom containers used in the app */
    .cover-slide-ticker {
        text-align: center !important;
        font-size: 3.5rem !important;
        font-weight: 700 !important;
        margin: 40px 0 !important;
        color: var(--text-primary) !important;
        letter-spacing: -0.03em !important;
    }
    
    .cover-slide-subtitle {
        text-align: center !important;
        font-size: 1.5rem !important;
        color: var(--text-tertiary) !important;
        margin-bottom: 30px !important;
        letter-spacing: 0.02em !important;
        font-weight: 400 !important;
    }
</style>
"""

# --- Other Constants ---
NEWS_TOKEN_FILENAME_TEMPLATE = "{ticker}_news_tokens.json"
NEWS_RANKED_FILENAME_TEMPLATE = "{ticker}_news_ranked.json"
PPT_FILENAME_TEMPLATE = "{ticker}_financial_report.pptx"