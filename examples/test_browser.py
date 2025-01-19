import asyncio
from peruse import BrowserAgent, LLMConfig
from peruse.utils import load_api_keys
from rich.console import Console

console = Console()

async def main():
    # Load API keys
    api_keys = load_api_keys()
    
    # Configure LLM (using Ollama for local execution)
    # llm_config = LLMConfig(
    #     provider="ollama",
    #     model="mistral"
    # )
    llm_config = LLMConfig(
        provider="anthropic",
        model="claude-3-5-sonnet-20240620",
        api_key=api_keys["anthropic"]
    )


    # Initialize browser agent
    agent = BrowserAgent(llm_config)
    await agent.setup()

    try:
        # Execute natural language commands
        commands = [
            "Go to google.com",
            "Search for 'Python programming' and wait for results",
            "Find the first link about Python's official website and click it",
            "Scroll down the page and tell me what sections you see"
        ]

        for command in commands:
            console.print(f"\nExecuting: {command}")
            result = await agent.execute(command)
            console.print(f"[bold green]Result:[/bold green] {result}")
            await asyncio.sleep(2)  # Small delay between commands
            
    finally:
        await agent.close()

if __name__ == "__main__":
    asyncio.run(main()) 