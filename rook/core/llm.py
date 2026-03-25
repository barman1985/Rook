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
import time
from collections import deque
import anthropic

from rook.core.config import cfg

logger = logging.getLogger(__name__)


class _OllamaMetrics:
    """Track Ollama performance for adaptive routing. Ported from Jarvis orchestrator."""

    def __init__(self, window_size: int = 10, cooldown_secs: int = 600):
        self.window_size = window_size
        self.cooldown_secs = cooldown_secs
        self.call_times: deque = deque(maxlen=window_size)
        self.results: deque = deque(maxlen=window_size)
        self._cooldown_until = 0.0

    def record_success(self, duration: float):
        self.call_times.append(duration)
        self.results.append(True)

    def record_failure(self, duration: float):
        self.call_times.append(duration)
        self.results.append(False)
        if len(self.results) >= 3:
            fail_rate = sum(1 for r in self.results if not r) / len(self.results)
            if fail_rate > 0.3:
                self._cooldown_until = time.time() + self.cooldown_secs
                logger.warning(f"Ollama cooldown: {fail_rate:.0%} fail rate → bypassing for {self.cooldown_secs}s")

    def should_use(self) -> bool:
        if time.time() < self._cooldown_until:
            return False
        if len(self.call_times) >= 3:
            avg = sum(self.call_times) / len(self.call_times)
            if avg > 5.0:
                self._cooldown_until = time.time() + self.cooldown_secs
                logger.warning(f"Ollama cooldown: avg latency {avg:.1f}s")
                return False
        return True


_ollama_metrics = _OllamaMetrics()


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
        # Try Ollama first — only if not in cooldown
        if cfg.ollama_enabled and _ollama_metrics.should_use():
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
        """Try local Ollama for classification. Returns None on failure. Tracks metrics."""
        start = time.time()
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
            duration = time.time() - start
            if resp.status_code != 200:
                _ollama_metrics.record_failure(duration)
                return None
            result = resp.json().get("response", "").strip()
            if result:
                _ollama_metrics.record_success(duration)
                logger.debug(f"Ollama classify: {result[:100]} ({duration:.2f}s)")
                return result
            _ollama_metrics.record_failure(duration)
            return None
        except Exception as e:
            _ollama_metrics.record_failure(time.time() - start)
            logger.debug(f"Ollama error: {e}")
            return None


# Singleton
llm = LLMClient()
