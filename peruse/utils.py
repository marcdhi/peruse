import os
from dotenv import load_dotenv

def load_api_keys():
    """Load API keys from environment variables or .env file"""
    load_dotenv()
    
    return {
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY")
    } 
