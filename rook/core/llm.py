"""
rook.core.llm — Multi-provider LLM client
=============================================
Supports Groq (FREE), Cerebras (FREE), and Anthropic (paid).
Auto-selects best available provider. Format conversion is transparent —
orchestrator always sees Anthropic-style responses.

Provider priority (benchmark-verified 2026-04-01):
  1. Groq Llama 4 Scout — 30 RPM burst, 1000 RPD, tool calling ✅
  2. Cerebras Qwen 235B — 14400 RPD, 8/8 quality, slower burst
  3. Anthropic — paid, highest quality, unlimited

Usage:
    from rook.core.llm import llm

    response = await llm.chat("What's the weather?", system="You are Rook.")
    response = await llm.chat_with_tools(messages, tools, system)
    text = await llm.classify("Is this a question?", system="Classify.")
"""

import json
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field as dc_field

from rook.core.config import cfg

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# ANTHROPIC-COMPATIBLE RESPONSE WRAPPERS
# (orchestrator expects .content[].type/.text/.name/.id/.input)
# ═══════════════════════════════════════════════════════════════

@dataclass
class _ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = dc_field(default_factory=dict)


@dataclass
class _TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class _Response:
    """Mimics anthropic.types.Message so orchestrator works unchanged."""
    content: list = dc_field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# FORMAT CONVERSION: Anthropic ↔ OpenAI
# ═══════════════════════════════════════════════════════════════

def _tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool defs → OpenAI function format."""
    result = []
    for t in tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            }
        })
    return result


def _messages_to_openai(messages: list[dict], system: str = "") -> list[dict]:
    """Convert Anthropic message format → OpenAI format."""
    out = []
    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Anthropic tool_result blocks → OpenAI tool messages
        if role == "user" and isinstance(content, list):
            tool_results = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_result"]
            if tool_results:
                for tr in tool_results:
                    out.append({
                        "role": "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content": str(tr.get("content", ""))[:10000],
                    })
                continue

        # Anthropic assistant with tool_use blocks → OpenAI assistant + tool_calls
        if role == "assistant" and isinstance(content, list):
            text_parts = []
            tc_list = []
            for block in content:
                if hasattr(block, "type"):
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tc_list.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            }
                        })
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tc_list.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            }
                        })
            msg_out = {"role": "assistant", "content": " ".join(text_parts) or None}
            if tc_list:
                msg_out["tool_calls"] = tc_list
            out.append(msg_out)
            continue

        out.append({"role": role, "content": str(content) if content else ""})

    return out


def _openai_response_to_anthropic(resp) -> _Response:
    """Convert OpenAI chat completion → Anthropic-style _Response."""
    choice = resp.choices[0] if resp.choices else None
    if not choice:
        return _Response(content=[_TextBlock(text="(no response)")])

    msg = choice.message
    blocks = []

    if msg.content:
        blocks.append(_TextBlock(text=msg.content))

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            blocks.append(_ToolUseBlock(
                id=tc.id,
                name=tc.function.name,
                input=args,
            ))

    return _Response(content=blocks or [_TextBlock(text="")])


# ═══════════════════════════════════════════════════════════════
# OLLAMA METRICS (local fallback for classify)
# ═══════════════════════════════════════════════════════════════

class _OllamaMetrics:
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
            if sum(1 for r in self.results if not r) / len(self.results) > 0.3:
                self._cooldown_until = time.time() + self.cooldown_secs

    def should_use(self) -> bool:
        if time.time() < self._cooldown_until:
            return False
        if len(self.call_times) >= 3 and sum(self.call_times) / len(self.call_times) > 5.0:
            self._cooldown_until = time.time() + self.cooldown_secs
            return False
        return True


_ollama_metrics = _OllamaMetrics()

# Rate limiting for free providers (min seconds between calls)
_RATE_LIMITS = {"groq": 2.1, "cerebras": 5.0}
_last_call: dict[str, float] = {}


async def _rate_limit(provider: str):
    limit = _RATE_LIMITS.get(provider, 0)
    if limit > 0:
        wait = limit - (time.time() - _last_call.get(provider, 0))
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call[provider] = time.time()


# ═══════════════════════════════════════════════════════════════
# LLM CLIENT
# ═══════════════════════════════════════════════════════════════

class LLMClient:
    """Multi-provider async LLM client.

    Priority: Groq (free, burst OK) → Cerebras (free, quality) → Anthropic (paid).
    Format conversion is transparent — orchestrator always sees Anthropic-style responses.
    """

    def __init__(self):
        self._anthropic = None
        self._openai_clients: dict = {}
        self._active_provider = self._detect_provider()
        logger.info(f"LLM provider: {self._active_provider}")

    def _detect_provider(self) -> str:
        if cfg.groq_api_key:
            return "groq"
        if cfg.cerebras_api_key:
            return "cerebras"
        if cfg.anthropic_api_key:
            return "anthropic"
        return "anthropic"

    def _get_anthropic(self):
        if self._anthropic is None:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
        return self._anthropic

    def _get_openai_client(self, provider: str):
        if provider not in self._openai_clients:
            from openai import AsyncOpenAI
            if provider == "groq":
                self._openai_clients[provider] = AsyncOpenAI(
                    api_key=cfg.groq_api_key, base_url=cfg.groq_base_url, max_retries=0,
                )
            elif provider == "cerebras":
                self._openai_clients[provider] = AsyncOpenAI(
                    api_key=cfg.cerebras_api_key, base_url=cfg.cerebras_base_url, max_retries=0,
                )
        return self._openai_clients[provider]

    def _get_model(self, provider: str, model_override: str = "") -> str:
        if model_override and not model_override.startswith("claude"):
            return model_override
        if provider == "groq":
            return cfg.groq_model
        if provider == "cerebras":
            return cfg.cerebras_model
        return cfg.main_model

    def _get_fallback(self, current: str) -> str | None:
        chain = ["groq", "cerebras", "anthropic"]
        keys = {"groq": cfg.groq_api_key, "cerebras": cfg.cerebras_api_key, "anthropic": cfg.anthropic_api_key}
        found = False
        for p in chain:
            if p == current:
                found = True
                continue
            if found and keys.get(p):
                return p
        return None

    async def chat(
        self,
        user_message: str,
        system: str = "",
        model: str = None,
        max_tokens: int = 2048,
    ) -> str:
        """Simple chat — returns text response."""
        provider = self._active_provider

        if provider == "anthropic":
            client = self._get_anthropic()
            response = await client.messages.create(
                model=model or cfg.main_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        await _rate_limit(provider)
        client = self._get_openai_client(provider)
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user_message})

        try:
            resp = await client.chat.completions.create(
                model=self._get_model(provider, model),
                messages=msgs,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            fallback = self._get_fallback(provider)
            if fallback:
                logger.warning(f"{provider} error: {e} → fallback {fallback}")
                old = self._active_provider
                self._active_provider = fallback
                try:
                    return await self.chat(user_message, system, model, max_tokens)
                finally:
                    self._active_provider = old
            raise

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        model: str = None,
        max_tokens: int = 2048,
    ):
        """Chat with tool use — returns Anthropic-style response (always)."""
        provider = self._active_provider

        if provider == "anthropic":
            client = self._get_anthropic()
            return await client.messages.create(
                model=model or cfg.main_model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )

        await _rate_limit(provider)
        client = self._get_openai_client(provider)
        openai_msgs = _messages_to_openai(messages, system)
        openai_tools = _tools_to_openai(tools) if tools else None

        kwargs = {
            "model": self._get_model(provider, model),
            "messages": openai_msgs,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        try:
            resp = await client.chat.completions.create(**kwargs)
            return _openai_response_to_anthropic(resp)
        except Exception as e:
            fallback = self._get_fallback(provider)
            if fallback:
                logger.warning(f"{provider} error: {e} → fallback {fallback}")
                old = self._active_provider
                self._active_provider = fallback
                try:
                    return await self.chat_with_tools(messages, tools, system, model, max_tokens)
                finally:
                    self._active_provider = old
            raise

    async def classify(
        self,
        user_message: str,
        system: str = "",
        max_tokens: int = 500,
    ) -> str:
        """Quick classification. Tries Ollama → active provider."""
        if cfg.ollama_enabled and _ollama_metrics.should_use():
            try:
                result = await self._classify_via_ollama(user_message, system)
                if result:
                    return result
            except Exception:
                pass
        return await self.chat(user_message, system=system, max_tokens=max_tokens)

    async def _classify_via_ollama(self, user_message: str, system: str = "") -> str | None:
        start = time.time()
        try:
            import httpx
            prompt = f"{system}\n\nUser: {user_message}" if system else user_message
            async with httpx.AsyncClient(timeout=cfg.ollama_timeout) as client:
                resp = await client.post(
                    f"{cfg.ollama_url}/api/generate",
                    json={"model": cfg.ollama_model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.1, "num_predict": 500}},
                )
            duration = time.time() - start
            if resp.status_code != 200:
                _ollama_metrics.record_failure(duration)
                return None
            result = resp.json().get("response", "").strip()
            if result:
                _ollama_metrics.record_success(duration)
                return result
            _ollama_metrics.record_failure(duration)
            return None
        except Exception:
            _ollama_metrics.record_failure(time.time() - start)
            return None


# Singleton
llm = LLMClient()
