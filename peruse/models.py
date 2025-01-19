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