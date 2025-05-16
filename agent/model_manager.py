# model_manager.py
from openai import OpenAI
import os

class ModelManager:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        
        # Define model configurations for different tasks
        self.model_configs = {
            "ticker_resolver": {
                "model": "gpt-3.5-turbo",  # Cheaper model for simple task
                "temperature": 0.1,
                "max_tokens": 500
            },
            "fact_extraction": {
                "model": "gpt-3.5-turbo-16k",  # Larger context for parsing articles
                "temperature": 0.0,  # Zero temperature for deterministic extraction
                "max_tokens": 2000
            },
            "ranking": {
                "model": "gpt-3.5-turbo",  # Simple ranking task
                "temperature": 0.2,
                "max_tokens": 2000
            },
            "analysis": {
                "model": "gpt-4o",  # Most capable model for the core analysis
                "temperature": 0.7,  # Allow some creativity
                "max_tokens": 4000
            },
            "macro_analysis": {
                "model": "gpt-3.5-turbo-16k",  # Good for analyzing macroeconomic trends
                "temperature": 0.3,
                "max_tokens": 2000
            }
        }
    
    def invoke_model(self, task, prompt, system_message=None, response_format=None):
        """Invoke the appropriate model for a given task"""
        if task not in self.model_configs:
            raise ValueError(f"Unknown task: {task}. Available tasks: {list(self.model_configs.keys())}")
        
        config = self.model_configs[task]
        
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Handle string prompts or message arrays
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        else:
            messages.extend(prompt)
        
        # Set up common parameters
        params = {
            "model": config["model"],
            "messages": messages,
            "temperature": config.get("temperature", 0.7),
            "max_tokens": config.get("max_tokens", 2000)
        }
        
        # Add response_format if specified
        if response_format:
            params["response_format"] = response_format
        
        try:
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error calling model for task '{task}': {str(e)}")
            raise