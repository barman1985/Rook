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
        """Quick classification call. Tries Ollama first (free, local), falls back to Haiku."""
        # Try Ollama first
        if cfg.ollama_enabled:
            try:
                result = await self._classify_via_ollama(user_message, system)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Ollama fallback: {e}")

        return await self.chat(
            user_message,
            system=system,
            model=cfg.router_model,
            max_tokens=max_tokens,
        )

    async def _classify_via_ollama(self, user_message: str, system: str = "") -> str | None:
        """Try local Ollama for classification. Returns None on failure."""
        try:
            import httpx
            prompt = f"{system}\n\nUser: {user_message}" if system else user_message
            async with httpx.AsyncClient(timeout=cfg.ollama_timeout) as client:
                resp = await client.post(
                    f"{cfg.ollama_url}/api/generate",
                    json={
                        "model": cfg.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 500},
                    },
                )
            if resp.status_code != 200:
                return None
            result = resp.json().get("response", "").strip()
            logger.debug(f"Ollama classify: {result[:100]}")
            return result if result else None
        except Exception as e:
            logger.debug(f"Ollama error: {e}")
            return None


# Singleton
llm = LLMClient()
