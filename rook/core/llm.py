"""
rook.core.llm — LLM client abstraction
========================================
Single interface for all LLM calls. Today: Anthropic. Tomorrow: local fallback.

Usage:
    from rook.core.llm import llm

    response = await llm.chat("What's the weather?", system="You are Rook.")
    response = await llm.chat_with_tools(messages, tools, system)
"""

import logging
import anthropic

from rook.core.config import cfg

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client with model routing."""

    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)

    async def chat(
        self,
        user_message: str,
        system: str = "",
        model: str = None,
        max_tokens: int = 2048,
    ) -> str:
        """Simple chat — returns text response."""
        model = model or cfg.main_model
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        model: str = None,
        max_tokens: int = 2048,
    ):
        """Chat with tool use — returns full response object."""
        model = model or cfg.main_model
        return await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )

    async def classify(
        self,
        user_message: str,
        system: str = "",
        max_tokens: int = 500,
    ) -> str:
        """Quick classification call using router model (cheap, fast)."""
        return await self.chat(
            user_message,
            system=system,
            model=cfg.router_model,
            max_tokens=max_tokens,
        )


# Singleton
llm = LLMClient()
