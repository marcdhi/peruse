from typing import Optional, Union
import openai
import anthropic
from .models import LLMConfig

class LLMProvider:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.setup_client()

    def setup_client(self):
        """Setup the appropriate LLM client based on configuration"""
        if self.config.provider == "openai":
            self.client = openai.Client(api_key=self.config.api_key)
        elif self.config.provider == "anthropic":
            self.client = anthropic.Client(api_key=self.config.api_key)
        elif self.config.provider == "ollama":
            import ollama
            self.client = ollama
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.provider}")

    async def process_command(self, command: str, page) -> str:
        """Process a natural language command and return browser actions"""
        system_prompt = """You are a browser automation assistant. 
        Convert natural language commands into specific browser actions.
        Available actions: click, type, navigate, wait, scroll"""

        if self.config.provider == "openai":
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command}
                ]
            )
            return response.choices[0].message.content

        elif self.config.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.config.model,
                system=system_prompt,
                messages=[{"role": "user", "content": command}]
            )
            return response.content[0].text

        elif self.config.provider == "ollama":
            # Ollama's chat method is synchronous
            response = self.client.chat(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command}
                ]
            )
            return response['message']['content'] 