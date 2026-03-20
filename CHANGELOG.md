# Changelog

All notable changes to Rook will be documented in this file.

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
