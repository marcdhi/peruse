from playwright.async_api import async_playwright
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from rich.console import Console
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel, Field
from .models import LLMConfig
import json
import random
from playwright_stealth import stealth_async
import asyncio
import subprocess
import psutil
import time
import os

console = Console()

class BrowserAction(BaseModel):
    """Base class for browser actions"""
    name: str = Field(..., description="Name of the action")
    description: str = Field(..., description="Description of what the action does")

class NavigateInput(BrowserAction):
    url: str = Field(..., description="URL to navigate to")
    name: str = "navigate"
    description: str = "Navigate to a specified URL"

class ClickInput(BrowserAction):
    selector: str = Field(..., description="CSS selector of element to click")
    name: str = "click"
    description: str = "Click an element on the page"

class TypeInput(BrowserAction):
    selector: str = Field(..., description="CSS selector of input field")
    text: str = Field(..., description="Text to type into the field")
    name: str = "type"
    description: str = "Type text into an input field"

class GetTextInput(BrowserAction):
    selector: str = Field(..., description="CSS selector of element to get text from")
    name: str = "get_text"
    description: str = "Get text content from an element"

class FindElementInput(BrowserAction):
    description: str = Field(..., description="Description of what you're looking for (e.g., 'search box', 'submit button')")
    name: str = "find_element"
    description: str = "Find an element on the page using various strategies"

SYSTEM_PROMPT = """You are a browser automation expert. Your task is to control a web browser to accomplish user objectives.
You have access to these tools:

- find_element: Find an element on the page using various strategies
- navigate: Navigate to a specified URL
- click: Click an element on the page using CSS selector
- type: Type text into an input field using CSS selector
- get_text: Get text content from an element using CSS selector

For complex tasks, break them down into individual steps. For example:
1. To search on Google:
   - First navigate to Google
   - Find the search box
   - Type in the search query
   - Find and click the search button

IMPORTANT: You must ALWAYS respond with ONLY a valid JSON object and nothing else. No natural language responses.
The JSON must follow this exact format:
{
    "tool": "tool_name",
    "args": {
        "arg1": "value1",
        ...
    }
}

Examples:
1. To find a search box:
{
    "tool": "find_element",
    "args": {
        "description": "search input box"
    }
}

2. To type in a found element:
{
    "tool": "type",
    "args": {
        "selector": "SELECTOR_FROM_FIND_ELEMENT",
        "text": "search query"
    }
}

Remember:
1. Respond with ONLY the JSON object, no other text
2. Execute one action at a time
3. Make sure the JSON is properly formatted
4. Use find_element to locate elements before interacting with them
"""

class LLMInterface:
    """Base class for LLM providers"""
    async def get_completion(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError

class OpenAIInterface(LLMInterface):
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def get_completion(self, messages: List[Dict[str, str]]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0
        )
        return response.choices[0].message.content

class AnthropicInterface(LLMInterface):
    def __init__(self, api_key: str, model: str):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def get_completion(self, messages: List[Dict[str, str]]) -> str:
        # Convert chat messages to Anthropic format
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"{msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += f"Human: {msg['content']}\n\n"
            elif msg["role"] == "assistant":
                prompt += f"Assistant: {msg['content']}\n\n"
        prompt += "Assistant: "

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

class BrowserAgent:
    def __init__(self, llm_config: LLMConfig, debug: bool = True):
        self.llm_config = llm_config
        self.browser = None
        self.playwright = None
        self.page = None
        self.llm: Optional[LLMInterface] = None
        self.action_history: List[Dict[str, Any]] = []
        self.debug = debug
        self.tools = {
            "navigate": self.navigate,
            "click": self.click,
            "type": self.type,
            "get_text": self.get_text,
            "find_element": self.find_element
        }

    def debug_print(self, message: str, level: str = "info"):
        """Print debug messages if debug mode is enabled"""
        if not self.debug:
            return
            
        colors = {
            "info": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "ai": "magenta"
        }
        
        console.print(f"[{colors.get(level, 'white')}]{message}[/{colors.get(level, 'white')}]")

    def _init_llm(self) -> LLMInterface:
        """Initialize the appropriate LLM based on config"""
        if self.llm_config.provider == "openai":
            return OpenAIInterface(
                api_key=self.llm_config.api_key,
                model=self.llm_config.model
            )
        elif self.llm_config.provider == "anthropic":
            return AnthropicInterface(
                api_key=self.llm_config.api_key,
                model=self.llm_config.model
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_config.provider}")

    async def setup(self):
        """Initialize the browser and LLM client"""
        console.print("[bold blue]Setting up browser agent...[/bold blue]")
        
        # Initialize async browser
        self.playwright = await async_playwright().start()
        
        try:
            # Use actual Chrome profile directory
            chrome_profile = os.path.expanduser("~/Library/Application Support/Google/Chrome")
            
            # Launch Chrome with absolute minimum flags
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            chrome_cmd = [
                chrome_path,
                f"--user-data-dir={chrome_profile}",
                "--remote-debugging-port=9222",
                "--no-first-run"
            ]
            
            self.debug_print("🚀 Launching Chrome with your profile...")
            self.chrome_process = subprocess.Popen(chrome_cmd)
            
            # Wait for Chrome to start
            self.debug_print("⏳ Waiting for Chrome to start...")
            time.sleep(5)
            
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    self.debug_print(f"🔄 Attempt {attempt + 1} to connect to Chrome...")
                    
                    # Connect to Chrome instance
                    self.browser = await self.playwright.chromium.connect_over_cdp(
                        "http://localhost:9222",
                        timeout=30000
                    )
                    
                    # Get existing context or create new one
                    contexts = self.browser.contexts
                    if contexts:
                        self.context = contexts[0]
                        self.debug_print("✅ Using existing browser context")
                    else:
                        self.debug_print("🆕 Creating new browser context")
                        self.context = await self.browser.new_context(
                            viewport={'width': 1920, 'height': 1080},
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
                        )

                    # Get existing page or create new one
                    pages = self.context.pages
                    if pages:
                        self.page = pages[0]
                        self.debug_print("✅ Using existing browser page")
                    else:
                        self.debug_print("🆕 Creating new browser page")
                        self.page = await self.context.new_page()
                    
                    # Apply basic stealth
                    await stealth_async(self.page)
                    
                    # Initialize LLM client
                    self.llm = self._init_llm()
                    
                    console.print("[bold green]Successfully connected to Chrome![/bold green]")
                    return
                    
                except Exception as e:
                    self.debug_print(f"❌ Attempt {attempt + 1} failed: {str(e)}", "warning")
                    if attempt < max_retries - 1:
                        self.debug_print(f"⏳ Retrying in {retry_delay} seconds...", "info")
                        await asyncio.sleep(retry_delay)
                    else:
                        console.print("[red]Failed to connect to Chrome after multiple attempts.[/red]")
                        if hasattr(self, 'chrome_process'):
                            self.chrome_process.kill()
                        raise
                        
        except Exception as e:
            self.debug_print(f"❌ Error during setup: {str(e)}", "error")
            # Clean up
            if hasattr(self, 'chrome_process'):
                self.chrome_process.kill()
            raise

    async def navigate(self, url: str) -> str:
        """Navigate to a URL"""
        self.debug_print(f"🌐 Navigating to {url}...")
        
        # Add https:// if not present
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
            
        try:
            # First try simple navigation
            response = await self.page.goto(url, timeout=30000)
            
            if not response:
                self.debug_print("⚠️ No response from navigation, trying alternative approach...")
                # Try alternative navigation method
                await self.page.evaluate(f"window.location.href = '{url}'")
                await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            
            # Wait for critical states with individual try-except blocks
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception as e:
                self.debug_print(f"⚠️ DOM content load timeout: {str(e)}")
                
            try:
                await self.page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                self.debug_print(f"⚠️ Network idle timeout: {str(e)}")
            
            # Verify navigation success
            current_url = self.page.url
            if not current_url or current_url == "about:blank":
                raise Exception("Navigation failed - page is blank")
                
            self.debug_print(f"✅ Successfully navigated to {current_url}")
            self.action_history.append({"action": "navigate", "url": url})
            return f"Navigated to {current_url}"
            
        except Exception as e:
            error_msg = f"❌ Error navigating to {url}: {str(e)}"
            self.debug_print(error_msg, "error")
            
            # Try one last time with a fresh page
            try:
                self.debug_print("🔄 Attempting navigation with fresh page...")
                await self.page.close()
                self.page = await self.context.new_page()
                await self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
                return f"Navigated to {url} (with fresh page)"
            except Exception as retry_error:
                raise Exception(f"{error_msg}\nRetry also failed: {str(retry_error)}")

    async def click(self, selector: str) -> str:
        """Click an element"""
        console.print(f"[cyan]Clicking element {selector}...[/cyan]")
        
        try:
            # Wait for element with explicit state checks
            element = await self.page.wait_for_selector(selector, 
                                                      state="visible",
                                                      timeout=5000)
            if not element:
                raise ValueError(f"Element not found: {selector}")
            
            # Ensure element is ready for interaction
            await element.wait_for_element_state("stable")
            await element.scroll_into_view_if_needed()
            
            # Click the element
            await element.click(delay=100)
            
            self.action_history.append({"action": "click", "selector": selector})
            return f"Clicked element matching {selector}"
            
        except Exception as e:
            console.print(f"[red]Error clicking element: {str(e)}[/red]")
            raise

    async def type(self, selector: str, text: str) -> str:
        """Type text into an input field"""
        self.debug_print(f"⌨️ Typing '{text}' into {selector}")
        
        try:
            # Wait for element with explicit state checks
            element = await self.page.wait_for_selector(selector, 
                                                      state="visible",
                                                      timeout=10000)
            if not element:
                raise ValueError(f"Element not found: {selector}")
            
            # Focus and clear the field
            await element.click()
            await self.page.wait_for_timeout(200)
            
            # Clear using keyboard shortcuts
            await self.page.keyboard.press("Control+A")
            await self.page.wait_for_timeout(100)
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(200)
            
            # Type text with small delays
            await element.type(text, delay=50)
            await self.page.wait_for_timeout(500)
            
            # Try to submit using Enter key
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_timeout(1000)
            
            # Wait for navigation to start
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                self.debug_print("✅ Navigation started")
                
                # Check if we're still on Google's main page
                current_url = self.page.url
                if "google.com" in current_url and not "search" in current_url:
                    self.debug_print("⚠️ Still on main page, trying search button...")
                    
                    # Try clicking the search button
                    button_selectors = [
                        "input[name='btnK']",
                        "input[value='Google Search']",
                        ".gNO89b",  # Google's search button class
                        "[aria-label='Google Search']"
                    ]
                    
                    for btn_selector in button_selectors:
                        try:
                            button = await self.page.wait_for_selector(btn_selector, 
                                                                     state="visible",
                                                                     timeout=2000)
                            if button:
                                await button.click()
                                await self.page.wait_for_load_state("domcontentloaded")
                                self.debug_print("✅ Search submitted via button")
                                break
                        except Exception:
                            continue
            
            except Exception as e:
                self.debug_print(f"⚠️ Navigation warning: {str(e)}")
            
            self.action_history.append({"action": "type", "selector": selector, "text": text})
            return f"Typed '{text}' into {selector} and submitted"
            
        except Exception as e:
            self.debug_print(f"❌ Error typing text: {str(e)}", "error")
            raise

    async def get_text(self, selector: str) -> str:
        """Get text content from an element"""
        console.print(f"[cyan]Getting text from {selector}...[/cyan]")
        # Wait for element to be visible
        await self.page.wait_for_selector(selector, state="visible")
        element = await self.page.query_selector(selector)
        if element:
            text = await element.text_content()
            self.action_history.append({"action": "get_text", "selector": selector, "result": text})
            return text
        return f"No element found matching {selector}"

    async def find_element(self, description: str) -> str:
        """Find an element on the page using various strategies"""
        self.debug_print(f"🔍 Finding element: {description}")
        
        # Debug: Print current page state
        self.debug_print(f"📄 Current URL: {self.page.url}")
        self.debug_print("⏳ Waiting for page to be stable...")
        
        try:
            # Wait for page to be stable
            await self.page.wait_for_load_state("domcontentloaded")
            await self.page.wait_for_load_state("networkidle")
        except Exception as e:
            self.debug_print(f"⚠️ Warning: Page load state error: {str(e)}", "warning")
        
        # Common selectors mapped to descriptions
        selector_maps = {
            "search": [
                # DuckDuckGo selectors
                "[name='q']",  # Generic search
                "#searchbox_input",  # New DuckDuckGo search
                "[data-testid='searchbox_input']", # Test ID selector
                "[type='text']",  # Generic text input
                "[type='search']",  # Generic search input
                "[role='searchbox']",  # ARIA role
                "input[placeholder*='search']",  # Placeholder search
                "input[placeholder*='Search']"  # Placeholder Search
            ],
            "button": [
                # DuckDuckGo selectors
                "[type='submit']",  # Generic submit
                "button[type='submit']",
                "[aria-label*='search' i]",  # Case insensitive search button
                "[aria-label*='Search' i]",
                "button[aria-label*='search' i]",
                "button[aria-label*='Search' i]"
            ]
        }
        
        # Determine which set of selectors to use
        selector_type = "search" if any(term in description.lower() for term in ["search", "input", "text"]) else "button"
        selectors = selector_maps[selector_type]
        
        self.debug_print(f"🎯 Using selectors for type '{selector_type}': {selectors}")
        
        # Try each selector
        for selector in selectors:
            try:
                self.debug_print(f"🔍 Trying selector: {selector}")
                
                # First check if element exists in DOM
                element = await self.page.wait_for_selector(selector, 
                                                          state="attached",
                                                          timeout=5000)  # Increased timeout
                if not element:
                    self.debug_print(f"❌ Selector {selector} not found in DOM", "warning")
                    continue
                
                # Check visibility
                is_visible = await element.is_visible()
                self.debug_print(f"👁️ Selector {selector} visible: {is_visible}")
                if not is_visible:
                    continue
                
                # Check if enabled
                is_enabled = await element.is_enabled()
                self.debug_print(f"🔓 Selector {selector} enabled: {is_enabled}")
                if not is_enabled:
                    continue
                
                # Debug: Print element properties
                box = await element.bounding_box()
                self.debug_print(f"📐 Element box: {box}")
                
                self.debug_print(f"✅ Found interactive element using selector: {selector}", "success")
                return selector
                
            except Exception as e:
                self.debug_print(f"❌ Error trying selector {selector}: {str(e)}", "error")
                continue
        
        raise ValueError(f"Could not find interactive element matching description: {description}")

    async def execute(self, command: str):
        """Execute a natural language command"""
        if not self.llm:
            raise RuntimeError("Agent not initialized. Call setup() first.")

        self.debug_print(f"🤖 Executing command: {command}", "ai")
        
        try:
            # Add context about current page
            current_url = self.page.url if self.page else "No page loaded"
            context = f"Current page: {current_url}\nCommand: {command}"
            
            self.debug_print("🧠 AI Context:", "ai")
            self.debug_print(context, "ai")
            
            # Get next action from LLM
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ]
            
            self.debug_print("🤔 Thinking...", "ai")
            response_text = await self.llm.get_completion(messages)
            self.debug_print(f"💭 AI Response: {response_text}", "ai")
            
            # Clean up response text and try to parse JSON
            try:
                # Remove any potential non-JSON text
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    action = json.loads(json_str)
                else:
                    raise ValueError("No JSON object found in response")

                self.debug_print(f"🎯 Parsed Action: {json.dumps(action, indent=2)}", "info")

                # Validate action format
                if not isinstance(action, dict) or "tool" not in action or "args" not in action:
                    raise ValueError("Invalid action format")
                if action["tool"] not in self.tools:
                    raise ValueError(f"Unknown tool: {action['tool']}")

                result = await self.tools[action["tool"]](**action["args"])
                self.debug_print(f"✅ Action Result: {result}", "success")
                
                # Wait for page to load/stabilize
                self.debug_print("⏳ Waiting for page to stabilize...", "info")
                await self.page.wait_for_load_state("networkidle")
                self.debug_print("✅ Page stable", "success")
                
                # For multi-step commands, we need to check if we're done
                messages.append({"role": "assistant", "content": str(action)})
                messages.append({
                    "role": "user", 
                    "content": f"Previous action result: {result}\nCurrent URL: {self.page.url}\nAre we done with the command: {command}? If not, what's the next step? Respond with a new action JSON or 'DONE' if complete."
                })
                
                self.debug_print("🤔 Checking if more steps needed...", "ai")
                next_response = await self.llm.get_completion(messages)
                self.debug_print(f"💭 AI Response: {next_response}", "ai")
                
                if "DONE" not in next_response.upper():
                    self.debug_print("⏭️ More steps needed, continuing...", "info")
                    return await self.execute(command)
                
                self.debug_print("✨ Command completed successfully!", "success")
                return result
                
            except json.JSONDecodeError as e:
                self.debug_print(f"❌ Failed to parse LLM response as JSON: {response_text}", "error")
                raise ValueError(f"Invalid JSON response from LLM: {str(e)}")
            except Exception as e:
                self.debug_print(f"❌ Error processing LLM response: {str(e)}", "error")
                raise
            
        except Exception as e:
            self.debug_print(f"❌ Error executing command: {str(e)}", "error")
            raise

    async def close(self):
        """Close the browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if hasattr(self, 'chrome_process'):
            self.chrome_process.kill()
        console.print("[bold blue]Browser closed.[/bold blue]") 