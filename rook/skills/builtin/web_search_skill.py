"""
Built-in skill: Web search
============================
Search the web using Anthropic's built-in web_search tool.
"""

from rook.skills.base import Skill, tool


class WebSearchSkill(Skill):
    name = "web_search"
    description = "Search the web for current information"
    version = "1.0"

    @tool(
        "web_search",
        "Search the internet for current information, news, or facts",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"},
        }, "required": ["query"]}
    )
    def search(self, query: str) -> str:
        # Note: This is a placeholder. In production, Anthropic's
        # built-in web_search tool handles this natively through
        # the tool_use API. This skill exists to register the tool
        # definition so the LLM knows it's available.
        return f"[web_search is handled natively by the LLM API]"


skill = WebSearchSkill()
