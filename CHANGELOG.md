# Changelog

All notable changes to Rook will be documented in this file.

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
