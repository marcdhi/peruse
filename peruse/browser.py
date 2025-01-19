from playwright.async_api import async_playwright
from typing import Optional, Union
from .models import LLMConfig, BrowserConfig
from .llm import LLMProvider

class Browser:
    def __init__(
        self,
        llm_config: LLMConfig,
        browser_config: Optional[BrowserConfig] = None,
        playwright=None,
        browser=None,
        page=None
    ):
        self.llm = LLMProvider(llm_config)
        self.browser_config = browser_config or BrowserConfig()
        self.playwright = playwright
        self.browser = browser
        self.page = page

    @classmethod
    async def create(
        cls,
        llm_config: LLMConfig,
        browser_config: Optional[BrowserConfig] = None
    ):
        """Factory method to create a Browser instance"""
        self = cls(llm_config, browser_config)
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.browser_config.headless
        )
        self.page = await self.browser.new_page()
        return self

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
        # Parse command using LLM and execute corresponding browser actions
        response = await self.llm.process_command(command, self.page)
        return response

    async def close(self):
        """Close the browser"""
        await self.browser.close()
        await self.playwright.stop() 