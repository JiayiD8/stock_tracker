# financial_analyzer.py
import json
import re
import os
import tiktoken
from model_manager import ModelManager

def num_tokens_from_string(string, encoding_name="cl100k_base"):
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens



def generate_financial_report(ticker, cached_data, macro_news, stock_cache, api_key, status_text):
    """Generate a comprehensive financial report using a multi-model approach"""
    status_text.text("Generating financial report using specialized models...")
    
    # Initialize model manager
    model_manager = ModelManager(api_key)
    
    # Step 1: Extract facts from news articles
    status_text.text("Extracting key facts from news articles...")
    fact_extraction_prompt = f"""
    Extract only objective facts from these news articles about {ticker}. 
    Focus on:
    1. Financial metrics and numbers
    2. Company announcements
    3. Product launches or changes
    4. Leadership changes
    5. Regulatory developments
    
    Format each fact as:
    - [FACT]: The specific fact
    - [SOURCE]: Brief indicator of which article (just the title or URL)
    
    DO NOT include opinions or interpretations.
    
    Articles:
    {cached_data}
    """
    
    extracted_facts = model_manager.invoke_model("fact_extraction", fact_extraction_prompt)
    
    # Step 1: Process macro news separately
    status_text.text("Analyzing macroeconomic trends...")
    macro_prompt = f"""
    You are an Economic Analyst reviewing the latest news articles. Base on the news Only Return me Below information:
    YOU Are analyzing for the economic/federal reserve/president policy that impact the macroeconomic 
    environment. Read the text that reports economic/political/national news, focusing on macro trends.
    
    ###### Report Format ######
    # Part1. Key takeaways of each economic/political news article.
    # Part2. What is the impact of the news on the economy?
    # Part3. What is the potential implication of the news on the stock market?
    
    Format as numbered points:
    1. Events(Part1) + Impact(Part2) + Impact on Stock(Part3)
    2. Events(Part1) + Impact(Part2) + Impact on Stock(Part3)
    etc.
    
    Here is the news:
    {macro_news}
    """
    
    macro_report = model_manager.invoke_model("macro_analysis", macro_prompt)
    
    # Step 3: Generate final financial report
    status_text.text("Creating comprehensive financial analysis...")
    final_prompt = f"""
    ## Prompt: Imagine yourself as a senior broker, analyst, and fund manager. 

    ### Here is the MacroEconomic News:
    {macro_report} 
    (very important, you need to read this first, and then you can read the following news)
    (all you analyst, evluation should be on the macro term / events/ policy)
    (You should analys the general trend about economy, then to stock market up/down)
    (then you start to read the news to think during this Macro/Political/Events time what ticker will behavior given the news)

    ### Here are the extracted key facts about {ticker}:
    {extracted_facts}

    ## Ticker Stock Price and Volatility:
    {stock_cache}

    ## For this ticker, create a detailed financial report with these sections:
    You are an financial report analyst. Write a detailed financial report based on the given information.
    All your read articels are already ranked, refine, so each of they are important for the report.
    The report should be detailed and comprehensive, covering all aspects of the company's financial health and future outlook.
    You are an very casution suspicious analyst, so you don not report as you read, but you inversely think why these article talk about this way, and what is the real situation behind the scene (inversely)

    ################################# Start of the report ######################################### (you don need to write this line)

    Your output should follow the exact format below:

    Section 1: Three Key take away from all articles read 
    For each takeaway, include the URL of a supporting article in [brackets] at the end.
    1.#xxxx(make up an subtitle): xxxxxxx [URL of supporting article]
    2.#xxxx(make up an subtitle): xxxxxxx [URL of supporting article]
    3.#xxxx(make up an subtitle): xxxxxxx [URL of supporting article]

    Section 2: Macro Situation and Stock Prospects 
    1.# Macro Situation(this is Subtitle one): Comprehensive summary of macroeconomic factors
    2.# Future Prospects(this is Subtitle two): Analysis of how macro factors will affect stock price

    Section 3: Catalyst 
    1.#Catalyst 1(this is Subtitle one): xxxxxxx
    2.#Catalyst 2(this is Subtitle two): xxxxxxx
    3.#Catalyst 3(this is Subtitle two): xxxxxxx
    4.#so on to add more if necessary (this is Subtitle more): xxxxxxx

    Section 4: Stock Price and Volatility Analysis 
    1. #Stock Price Analysis(this is Subtitle one): xxxxxxx
    2. #Volatility Analysis(this is Subtitle two): xxxxxxx
    3. #What They Reflect in Term of Investor(this is Subtitle three): xxxxxxx
    
    Section 5: Investment Recommendation 
    1. #What Position We Should Take (this is Subtitle one): xxxxxxx
    2. #What Price Target (this is Subtitle two): xxxxxxx
    3. #Why We Should Take This Position (this is Subtitle three): xxxxxxx
    4. #What Are The Potential Risks (this is Subtitle four): xxxxxxx
    
    For each section of the report, apply this chain-of-thought process:
    1. First, list the specific evidence from news articles that supports your analysis
    2. Then, explain what conventional analysis would typically conclude
    3. Next, explain why this conventional analysis might be incomplete or misleading
    4. Finally, provide your distinctive insight that goes beyond the surface-level observation

    This will ensure your analysis is evidence-based, distinctive, and avoids generic statements that could apply to any company.

    ################################# End of the report #########################################  (you don need to write this line)
    
    You sould at the beginning highliht the most three important news/aspect, and I want details written manner. Where you dont describe the information, but every sentence you need to use casual inference to report as what/how/why. 
    No sensentence should be left without a events/reason plus the number/people 
    Note: The symbol '#' is important for late where I input this txt file to next pipeline to detect the content and title, so please keep it.
    Note: The subtitle is important for the next pipeline to detect the content and title, so keep it in same upper case lower case as I define.
    """
    
    financial_report = model_manager.invoke_model("analysis", final_prompt)
    # debug_log(f"Financial report generated: {len(financial_report)} characters", status_text)
    print(f"Macro report: {macro_report[:100]}...")
    print(f"Financial report length: {len(financial_report)}")
    print(f"Financial report first 200 chars: {financial_report[:200]}")

    return financial_report

