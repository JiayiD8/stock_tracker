# stock_data.py
import yfinance as yf
from datetime import datetime, timedelta

def generate_stock_cache(ticker, n_days, status_text):
    """Fetch and format stock data for the specified ticker"""
    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=n_days)).strftime('%Y-%m-%d')

    if status_text:
        status_text.text(f"Fetching stock data for {ticker}...")
    
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(start=start_date, end=end_date, interval='1d')

        if data.empty:
            if status_text:
                status_text.text(f"No stock data found for {ticker}")
            return None

        # Calculate volatility
        data['Volatility'] = data['High'] - data['Low']
        
        # Format the data as a readable string
        stock_cache = []
        for date, row in data.iterrows():
            formatted_date = date.strftime('%m-%d-%Y')
            stock_cache.append(f"{formatted_date}: price: {row['Close']:.2f}, volatility: {row['Volatility']:.2f}, volume: {int(row['Volume'])}")

        return "\n".join(stock_cache)
    
    except Exception as e:
        if status_text:
            status_text.text(f"Error fetching stock data: {str(e)}")
        return None