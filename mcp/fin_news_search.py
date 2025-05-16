from typing import Any
import httpx
import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP
from bs4 import BeautifulSoup
import feedparser
import tiktoken

mcp = FastMCP("stock_news")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
TEMP_DIR = os.path.join(tempfile.gettempdir(), "stock_news_mcp")
os.makedirs(TEMP_DIR, exist_ok=True)

YAHOO_FINANCE_RSS = "https://finance.yahoo.com/rss/headline?s={symbol}"

def num_tokens_from_string(string, encoding_name="cl100k_base"):
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def extract_date(date_string):
    """Extract date from date string format."""
    try:
        cleaned_date_string = date_string.replace("GMT", "+0000")
        return datetime.strptime(cleaned_date_string, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return None

async def extract_news_content(url):
    """Extract the main content of a news article."""
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Find article body
            article_body = soup.find("article") or \
                        soup.find("div", class_=lambda c: c and any(x in c for x in ["article", "content", "story", "body", "text"])) or \
                        soup.find("main")
            
            if article_body:
                paragraphs = article_body.find_all("p")
                content = "\n".join([p.get_text(separator=' ', strip=True) for p in paragraphs])
            else:
                # Fallback to all paragraphs
                paragraphs = soup.find_all('p')
                content = "\n".join([para.get_text() for para in paragraphs])
                
            return content.strip() if content else "⚠ Unable to extract article content."
        except Exception as e:
            return f"⚠ Extraction failed: {str(e)}"

@mcp.tool()
async def search_stock_news(company_symbol: str, max_results: int = 5) -> str:
    """Search for recent Yahoo Finance news articles for a company.
    """
    if not company_symbol:
        return "Error: Please provide a company symbol."
    
    company_symbol = company_symbol.upper()
    rss_url = YAHOO_FINANCE_RSS.format(symbol=company_symbol)
    loop = asyncio.get_event_loop()
    feed = await loop.run_in_executor(None, feedparser.parse, rss_url)
    
    if not feed.entries:
        return f"No recent news found for {company_symbol} on Yahoo Finance."
    
    articles = feed.entries[:max_results]
    
    # Format the results
    result = f"Recent Yahoo Finance News for {company_symbol}:\n\n"
    for idx, item in enumerate(articles, 1):
        # Get publication date
        pub_date = item.get("published", "No Date")
        
        result += f"Article {idx}:\n"
        result += f"Title: {item.get('title', 'No Title')}\n"
        result += f"Published: {pub_date}\n"
        result += f"URL: {item.get('link', 'No URL')}\n"
        result += f"Summary: {item.get('summary', 'No summary available')}\n"
        
        if idx < len(articles):
            result += "\n---\n\n"
    
    return result

@mcp.tool()
async def get_news_content(news_url: str) -> str:
    """Retrieve the full content of a news article for summarization.
    """
    content = await extract_news_content(news_url)
    
    # Return the content
    if content.startswith("⚠"):
        return content
    
    # Calculate token count
    token_count = num_tokens_from_string(content)
    
    return f"Article Content ({token_count} tokens):\n\n{content}"

@mcp.tool()
async def get_company_news_with_content(company_symbol: str, max_articles: int = 5) -> str:
    """Search for Yahoo Finance news about a company and retrieve the full content of each article.
    """
    news_results = await search_stock_news(company_symbol, max_articles)
    
    if news_results.startswith("No recent news found"):
        return news_results
    
    urls = []
    for line in news_results.split('\n'):
        if line.startswith("URL: "):
            urls.append(line[5:])
    
    if not urls:
        return "No valid article URLs found in the search results."
    
    full_results = f"Yahoo Finance News for {company_symbol}:\n\n"
    
    for i, url in enumerate(urls, 1):
        article_section = news_results.split("---")[i-1] if i < len(urls) else news_results.split(f"Article {i}:")[1]
        
        title = ""
        published = ""
        for line in article_section.split('\n'):
            if line.startswith("Title: "):
                title = line[7:]
            elif line.startswith("Published: "):
                published = line[11:]
        
        article_content = await get_news_content(url)
        
        full_results += f"Article {i}:\n"
        full_results += f"Title: {title}\n"
        full_results += f"Published: {published}\n"
        full_results += f"URL: {url}\n\n"
        
        if "⚠" not in article_content:
            content_text = article_content.split("\n\n", 1)[1] if "\n\n" in article_content else article_content
            full_results += f"{content_text}\n"
        else:
            full_results += f"{article_content}\n"
        
        full_results += "\n" + "="*50 + "\n\n"
    
    return full_results

if __name__ == "__main__":
    mcp.run(transport='stdio')