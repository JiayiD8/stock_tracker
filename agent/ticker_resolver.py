# ticker_resolver.py
import json
import yfinance as yf
from openai import OpenAI

def get_basic_info(ticker_symbol):
    """Get basic info about a ticker to validate if it exists"""
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
            return {
                "valid": True,
                "ticker": ticker_symbol,
                "name": info.get('shortName', ''),
                "current_price": info.get('regularMarketPrice', 'N/A')
            }
        return {"valid": False}
    except Exception as e:
        print(f"Error checking {ticker_symbol}: {str(e)}")
        return {"valid": False}

def ai_ticker_resolver(input_text, api_key):
    """Use OpenAI to identify stock ticker from user input"""
    client = OpenAI(api_key=api_key)
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # You can use cheaper models like gpt-3.5-turbo for this task
            messages=[
                {"role": "system", "content": "You are a financial assistant that helps identify stock ticker symbols."},
                {"role": "user", "content": f"""
                The user has entered: "{input_text}"
                
                If this is already a valid stock ticker symbol, confirm it.
                If this appears to be a company name or misspelled ticker, identify the most likely correct ticker symbol.
                If there are multiple possibilities, list the most likely options (max 3).
                
                Include major US stocks, but also global exchanges (add exchange suffix if non-US).
                
                Respond in this JSON format:
                {{
                    "is_valid_ticker": true/false,
                    "input": "what the user entered",
                    "best_match": "TICKER",
                    "company_name": "Company Name",
                    "alternatives": [
                        {{"ticker": "ALT1", "name": "Alternative Company 1"}},
                        {{"ticker": "ALT2", "name": "Alternative Company 2"}}
                    ],
                    "confidence": 0-100
                }}
                """}
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.1  # Keep it deterministic
        )
        
        ai_result = json.loads(response.choices[0].message.content)
        
        # Verify the suggested ticker actually exists
        if ai_result.get("best_match"):
            verification = get_basic_info(ai_result["best_match"])
            ai_result["verified"] = verification["valid"]
            
            if verification["valid"]:
                ai_result["company_name"] = verification["name"]
                ai_result["current_price"] = verification["current_price"]
        
        # Verify alternatives too
        verified_alternatives = []
        for alt in ai_result.get("alternatives", []):
            alt_verify = get_basic_info(alt["ticker"])
            if alt_verify["valid"]:
                alt["verified"] = True
                alt["current_price"] = alt_verify["current_price"]
                alt["name"] = alt_verify["name"]  # Use actual name from yfinance
                verified_alternatives.append(alt)
        
        ai_result["alternatives"] = verified_alternatives
        
        return ai_result
    
    except Exception as e:
        print(f"Error in AI ticker resolution: {str(e)}")
        return {
            "is_valid_ticker": False,
            "input": input_text,
            "best_match": None,
            "alternatives": [],
            "confidence": 0,
            "error": str(e)
        }

def resolve_ticker(input_text, api_key):
    """Master function to resolve ticker symbols"""
    # First check if the input is already a valid ticker
    direct_check = get_basic_info(input_text.upper())
    
    if direct_check["valid"]:
        return {
            "is_valid_ticker": True,
            "input": input_text,
            "best_match": input_text.upper(),
            "company_name": direct_check["name"],
            "current_price": direct_check["current_price"],
            "alternatives": [],
            "confidence": 100,
            "verified": True
        }
    
    # If not a valid ticker, use AI to resolve
    return ai_ticker_resolver(input_text, api_key)