# Changelog

All notable changes to Rook will be documented in this file.

## [2.1.0] — 2026-04-01

### Changed — Multi-Provider LLM Architecture (FREE tier support)

- **LLM client rewrite** (`core/llm.py`) — Multi-provider support with automatic fallback chain. Groq (free) → Cerebras (free) → Anthropic (paid). Format conversion is transparent — orchestrator unchanged.
- **New default providers** — Groq Llama 4 Scout (primary, 30 RPM burst, 1000 req/day) and Cerebras Qwen 235B (fallback, 14400 req/day). Both free, no credit card needed. Anthropic now optional.
- **Config updated** (`core/config.py`) — Added `GROQ_API_KEY`, `GROQ_MODEL`, `CEREBRAS_API_KEY`, `CEREBRAS_MODEL`. Validation accepts any provider (not just Anthropic).
- **Rate limiting** — Built-in per-provider rate limiting (2.1s Groq, 5.0s Cerebras) prevents 429 errors in agent loops.
- **Automatic fallback** — On provider error/429, silently falls back to next available provider. No user-visible interruption.
- **OpenAI-compatible wrapper** — Response objects mimic Anthropic format (`_Response`, `_TextBlock`, `_ToolUseBlock`), so `orchestrator.py` works with any provider without changes.
- **Documentation** — Updated README Quick start, .env.example, requirements.txt. Groq/Cerebras prominently featured as recommended free setup.

### Architecture decisions (benchmark-verified 2026-04-01)

10 models tested × 8 tests (tool calling, memory, empathy, anti-hallucination, disambiguation, Czech):
- Cerebras Qwen 235B: 8/8 (best quality, but 1 req/5s burst limit)
- Groq Qwen3 32B: 7/8, Groq Kimi K2: 7/8
- Groq Llama 4 Scout: 6/8 (chosen for primary — best burst tolerance)
- Mistral Large: 4/8 (hallucinates — excluded from agent brain)
- Gemini 2.5 Flash: 0/8 (20 req/day — unusable)

## [2.0.0] — 2026-04-01

### Added — Rook 2.0: Intelligence Layer

- **Graph Memory** (`core/graph_memory.py`) — Entity-relation knowledge graph. Stores subject-predicate-object triples with confidence scoring. Upsert on duplicate, full-text search, prompt injection.
- **Emotional Memory** (`core/emotional_memory.py`) — Tracks valence/arousal/dominance per session via regex-based structural analysis (zero API cost). Session consolidation into persistent imprints. Mode detection (focused/playful/stressed/deep_talk). Quote book. Czech + English emotion patterns.
- **Metacognition** (`core/metacognition.py`) — Bayesian confidence tracking per domain using Beta distribution. Records task outcomes, estimates confidence with credible intervals, generates calibration reports. Rook knows what it's good at.
- **Self-Improvement** (`skills/builtin/self_improve_skill.py`) — Rook reads, analyzes, and proposes changes to its own source code. Full pipeline: read_source → propose_change → diff → /approve or /reject → py_compile check → git commit. Safety: path sandboxing (rook/ only), max 3/day, rollback on failure.
- **Knowledge Broker** (`core/knowledge_broker.py`) — Trust system for A2A communication. Default trust 0.3, adjustable by exchange quality. Outgoing sanitization (API keys, emails, phone numbers). Incoming injection detection. Rate limiting per agent.
- **A2A Communication** (`core/a2a.py`) — Google A2A protocol (JSON-RPC 2.0 over HTTP). Agent card at `/.well-known/agent.json`. Peer discovery, registration, outgoing/incoming message handling. Trust-gated via Knowledge Broker. Proactive outreach scheduler.
- **Proactive Discovery** (`services/discovery.py`) — RSS feed scanning 4×/day. Relevance scoring via LLM classify (FREE). Max 3 notifications/day. Default sources: Hacker News, Ars Technica, r/LocalLLaMA. User can add/remove sources.
- **47 new tests** (`tests/test_rook2.py`) — Comprehensive coverage for all 7 new modules.

### Changed

- `core/db.py`: 8 new tables — knowledge_graph, emotional_imprints, emotional_quotes, metacognition, capability_log, a2a_peers, a2a_exchanges, discovery_items, discovery_sources. Indexes on knowledge_graph subject/object.
- `services/prompt.py`: System prompt now injects emotional context, metacognitive brief, knowledge graph, and recent discoveries. Safe loading with graceful fallback.
- `services/scheduler.py`: Added discovery job (4×/day at 6:00, 10:00, 14:00, 18:00) and emotional consolidation (daily at 23:00).

### Architecture

```
Transport (Telegram/MCP)
    ↓
Router (Orchestrator — agentic tool loop)
    ↓
Skills (calendar, email, memory, spotify, self_improve, ...)
    ↓
Intelligence Layer [NEW]
    ├── Emotional Memory (session tracking, imprints)
    ├── Graph Memory (entity-relation triples)
    ├── Metacognition (Bayesian confidence)
    ├── Knowledge Broker (trust, sanitization)
    ├── A2A (peer communication)
    └── Discovery (RSS scanning)
    ↓
Core (Config, DB, LLM, Events, Memory)
```

## [0.2.1] — 2026-03-25

### Fixed
- **Language switching bug** — Rook no longer switches to the language of tool results (e.g. English email subjects) mid-conversation. SOUL.md now has an explicit universal language rule: always respond in the user's language, regardless of data source language.
- **Unsolicited commentary** — Rook no longer comments on side-effect data from tool calls (e.g. total unread email count) unless the user explicitly asked about it.
- **Conversation amnesia** — orchestrator now receives full conversation history (last 20 messages). Previously each message was processed without context.
- **Compaction language** — `_maybe_compact()` prompt rewritten to be language-neutral. Previously the summary was always generated in English, causing confusion in non-English conversations.
- **Ollama reliability** — `_classify_via_ollama()` now tracks success/failure metrics. Enters 10-minute cooldown after >30% failure rate or avg latency >5s, preventing repeated 15s timeouts when Ollama is unavailable.

### Added
- `tests/test_routing.py` — 16 new tests covering: `_OllamaMetrics` adaptive cooldown logic (9 tests), orchestrator `history` parameter and message assembly (4 tests, run on VPS with anthropic), SOUL.md language and commentary rules (3 tests).

### Changed
- `orchestrator.py`: `handle()` accepts optional `history` parameter. `MAX_ITERATIONS` raised from 10 to 12.
- `llm.py`: `_OllamaMetrics` class added with adaptive cooldown (ported from Jarvis).
- `email_skill.py`: tool result strings are now language-neutral structured format.
- `SOUL.md`: language rule made explicit and universal; anti-commentary rule added.

## [0.2.0] — 2026-03-23

### Added
- **SOUL.md** — user-editable personality file. Prompt builder loads it with mtime cache, auto-reloads on change. No restart needed.
- **Conversation compaction** — after 50 messages, summarizes history and purges old messages. DB no longer grows infinitely.
- **Ollama fallback** — optional local LLM for router classification. Config: `OLLAMA_ENABLED`, `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`. Falls back to Haiku on failure.
- **Home Assistant community skill** — 4 tools: `hass_get_state`, `hass_call_service`, `hass_list_entities`, `hass_overview`. REST API integration with Long-Lived Access Token. First community skill example.
- **Heartbeat system** — every hour during active hours (7:30-21:30), reads `HEARTBEAT.md` checklist, gathers context (calendar, email), asks LLM if anything needs attention. Silent if nothing.
- **Skill dependency validation** — skills declare `requires_env` and `requires_pip`. Loader validates at startup and disables gracefully with clear message instead of crashing.
- `HEARTBEAT.md` — user-editable proactive checklist
- `db.py`: `get_message_count()`, `get_recent_messages()`, `delete_old_messages()`, `save_profile()`, `get_profile()`
- `llm.py`: `_classify_via_ollama()` async method with httpx
- `.env.example`: Home Assistant and Ollama configuration sections

### Changed
- `prompt.py`: loads SOUL.md dynamically instead of hardcoded personality
- `config.py`: added Ollama fields + `from_env()` loading + summary display
- `base.py`: added `requires_env`, `requires_pip`, `check_dependencies()`
- `loader.py`: validates skill dependencies before loading
- Architecture diagram in README updated
- README expanded with SOUL.md, Heartbeat, Home Assistant, Ollama sections

## [0.1.0] — 2026-03-20

### Added
- Initial release
- 5-layer architecture: Transport → Router → Skills → Event Bus → Core
- Core: Config, DB (SQLite/WAL), Event bus, LLM client, Memory (ACT-R)
- Skill system: `@tool` decorator, auto-discovery from builtin/ and community/
- Built-in skills: memory, web search
- Transport: Telegram bot with message chunking
- Router: agentic tool-use loop with model routing
- Docker support (Dockerfile + docker-compose)
- MIT license
