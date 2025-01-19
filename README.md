PERUSE - Browser Automation with LLMs
====================================

1. Package Structure
-------------------
peruse/
├── .github/
│   └── workflows/
│       └── publish.yml
├── examples/
│   └── test_browser.py
├── peruse/
│   ├── __init__.py
│   ├── browser.py
│   ├── llm.py
│   ├── models.py
│   └── utils.py
├── .env
├── LICENSE
├── README.md
└── pyproject.toml

2. File Contents
---------------

pyproject.toml:
--------------
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "peruse"
version = "0.0.1"
authors = [
  { name="Mardav Gandhi", email="gandhi.mardav@gmail.com" },
]
description = "A browser automation library powered by LLMs (local and cloud)"
readme = "README.md"
requires-python = ">=3.8"
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
]
dependencies = [
    "playwright>=1.39.0",
    "openai>=1.0.0",
    "anthropic>=0.5.0",
    "ollama>=0.1.0",
    "pydantic>=2.0.0"
]

[project.urls]
Homepage = "https://github.com/marcdhi/peruse"
Issues = "https://github.com/marcdhi/peruse/issues"

peruse/__init__.py:
------------------
from .browser import Browser
from .models import LLMConfig, BrowserConfig

__version__ = "0.0.1"
__all__ = ["Browser", "LLMConfig", "BrowserConfig"]

peruse/browser.py:
-----------------
from playwright.sync_api import sync_playwright
from typing import Optional, Union
from .models import LLMConfig, BrowserConfig
from .llm import LLMProvider

class Browser:
    def __init__(
        self,
        llm_config: LLMConfig,
        browser_config: Optional[BrowserConfig] = None
    ):
        self.llm = LLMProvider(llm_config)
        self.browser_config = browser_config or BrowserConfig()
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.browser_config.headless
        )
        self.page = self.browser.new_page()

    async def navigate(self, url: str):
        """Navigate to a URL"""
        await self.page.goto(url)

    async def click(self, selector: str):
        """Click an element"""
        await self.page.click(selector)

    async def type(self, selector: str, text: str):
        """Type text into an element"""
        await self.page.fill(selector, text)

    async def execute_command(self, command: str):
        """Execute a natural language command using LLM"""
        response = await self.llm.process_command(command, self.page)
        return response

    def close(self):
        """Close the browser"""
        self.browser.close()
        self.playwright.stop()

peruse/llm.py:
-------------
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
            response = await self.client.chat(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command}
                ]
            )
            return response['message']['content']

peruse/models.py:
---------------
from pydantic import BaseModel
from typing import Literal, Optional

class LLMConfig(BaseModel):
    provider: Literal["openai", "anthropic", "ollama"]
    model: str
    api_key: Optional[str] = None

class BrowserConfig(BaseModel):
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720

peruse/utils.py:
--------------
import os
from dotenv import load_dotenv

def load_api_keys():
    """Load API keys from environment variables or .env file"""
    load_dotenv()
    
    return {
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY")
    }

examples/test_browser.py:
-----------------------
import asyncio
from peruse import Browser, LLMConfig, BrowserConfig
from peruse.utils import load_api_keys

async def main():
    # Load API keys
    api_keys = load_api_keys()
    
    # Configure your preferred LLM
    llm_config = LLMConfig(
        provider="openai",
        model="gpt-4",
        api_key=api_keys["openai"]
    )

    # Optional browser configuration
    browser_config = BrowserConfig(
        headless=False,
        viewport_width=1280,
        viewport_height=720
    )

    # Initialize browser
    browser = Browser(llm_config, browser_config)

    try:
        # Test natural language commands
        await browser.execute_command("Go to google.com and search for 'Python programming'")
        
        # Or use direct browser actions
        await browser.navigate("https://www.google.com")
        await browser.type("input[name='q']", "Python programming")
        await browser.click("input[type='submit']")
        
        # Wait a bit to see results
        await asyncio.sleep(5)
        
    finally:
        browser.close()

if __name__ == "__main__":
    asyncio.run(main())

.env:
----
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

.github/workflows/publish.yml:
---------------------------
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.x'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish package
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*

3. Publishing Steps
------------------
1. Create PyPI account at https://pypi.org/account/register/
2. Generate API token at https://pypi.org/manage/account/token/
3. Add token to GitHub repository secrets as PYPI_API_TOKEN
4. Push code to GitHub
5. Create a release on GitHub
6. GitHub Actions will automatically publish to PyPI

4. Installation for Users
------------------------
pip install peruse
playwright install  # Install browser binaries

5. Usage Example
---------------
from peruse import Browser, LLMConfig

llm_config = LLMConfig(
    provider="openai",
    model="gpt-4",
    api_key="your-api-key"
)

browser = Browser(llm_config)
await browser.execute_command("Go to google.com and search for 'Python'")
browser.close()

6. Required Dependencies
-----------------------
pip install build twine playwright openai anthropic ollama pydantic python-dotenv

7. Testing
----------
1. Set up your .env file with API keys
2. Run: python examples/test_browser.py

8. Version Updates
-----------------
1. Update version in pyproject.toml and __init__.py
2. Create new GitHub release
3. GitHub Actions will handle publishing 