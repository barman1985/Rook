<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/banner.svg">
    <img alt="Rook" src="docs/banner.svg" width="420">
  </picture>
</p>

<p align="center">
  <strong>Your strategic AI advantage.</strong><br>
  <sub>Open-source personal AI assistant in Telegram</sub>
</p>

<p align="center">
  <a href="https://github.com/barman1985/Rook/stargazers"><img src="https://img.shields.io/github/stars/barman1985/Rook?style=flat&color=f97316" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-f97316" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11+-f97316" alt="Python"></a>
  <a href="https://github.com/barman1985/Rook/issues"><img src="https://img.shields.io/github/issues/barman1985/Rook?color=f97316" alt="Issues"></a>
  <a href="https://github.com/sponsors/barman1985"><img src="https://img.shields.io/badge/sponsor-♥-f97316" alt="Sponsor"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> •
  <a href="#features">Features</a> •
  <a href="#creating-a-skill">Create a skill</a> •
  <a href="#architecture">Architecture</a> •
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

---

Rook is an open-source personal AI assistant that lives in Telegram. It doesn't just answer questions — it manages your calendar, triages your email, controls your music, remembers your preferences, and proactively keeps you on track.

> *"Like having a chief of staff in your pocket."*

<!-- TODO: Add demo GIF here
<p align="center">
  <img src="docs/demo.gif" width="360" alt="Rook demo">
</p>
-->

---

## What makes Rook different

- **Actually does things** — not a chatbot. Rook creates calendar events, sends emails, controls Spotify, manages your smart home, and more.
- **Proactive, not reactive** — morning briefings, calendar reminders, and a heartbeat system that periodically checks if anything needs your attention.
- **Memory that works like yours** — ACT-R cognitive architecture: frequently accessed memories stay sharp, unused ones fade naturally. Conversation compaction keeps context without infinite DB growth.
- **User-editable personality** — edit `SOUL.md` to change how Rook communicates. No code, no restart, instant effect.
- **Smart home ready** — Home Assistant integration out of the box. Control lights, climate, sensors via natural language.
- **Local LLM fallback** — optional Ollama integration for router classification. Free, private, offline-capable.
- **Plugin system with dependency validation** — drop a Python file in `skills/community/`, declare what it needs, and Rook picks it up. Missing API key? Graceful disable, not a crash.
- **Telegram-native** — zero onboarding. No new app to install.

---

## Features

| Feature | Description |
|---------|-------------|
| 📅 **Calendar** | Create, edit, delete, search events (Google Calendar) |
| 📧 **Email** | Read, search, send emails (Gmail) |
| 🎵 **Spotify** | Play, search, playlists, device control |
| 📺 **TV** | Power, apps, volume (Chromecast) |
| 🏠 **Smart Home** | Home Assistant integration — lights, climate, sensors, any HA entity |
| 🧠 **Memory** | ACT-R activation scoring, decay, long-term recall, conversation compaction |
| 💓 **Heartbeat** | Periodic proactive check — "does anything need attention?" Silent if no. |
| 🔔 **Proactive** | Calendar reminders, morning briefings, evening summaries |
| 🎭 **SOUL.md** | User-editable personality, communication style, rules — no restart needed |
| 🎙️ **Voice** | Local STT (faster-whisper) + TTS (Piper) |
| 🤖 **Ollama** | Optional local LLM fallback for router (free, private) |
| 🌐 **Web search** | Current info via Anthropic web search |
| 🔌 **MCP Server** | Expose all tools to Claude Desktop, Cursor, etc. |
| 🧩 **Plugins** | Community skills with dependency validation, auto-discovered |

---

## Quick start

### Prerequisites

- Python 3.11+
- [Anthropic API key](https://console.anthropic.com/)
- [Telegram bot token](https://core.telegram.org/bots#how-do-i-create-a-bot)

### Install

```bash
git clone https://github.com/barman1985/Rook.git
cd Rook
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configure (interactive wizard)

```bash
python -m rook.setup
```

The wizard guides you through everything — API keys, optional integrations (Google, Spotify, TV, X), and installs dependencies. Takes about 2 minutes.

Or configure manually:

```bash
cp .env.example .env
# Edit .env with your API keys
```

### Run

```bash
python -m rook.main
```

### Docker (alternative)

```bash
docker-compose up -d
```

---

## Architecture

```
┌─────────────────────────────────┐
│       Transport layer           │  Telegram, MCP, CLI
├─────────────────────────────────┤
│       Router / Orchestrator     │  Intent → model → agent loop
│       (Ollama local fallback)   │  Classify via local LLM or Haiku
├─────────────────────────────────┤
│       Skill layer (pluggable)   │  Calendar, Email, Spotify, ...
│  ┌──────┐ ┌──────┐ ┌────────┐  │
│  │built │ │built │ │communit│  │  Drop a .py, declare deps, done.
│  │ -in  │ │ -in  │ │HomeAsst│  │
│  └──────┘ └──────┘ └────────┘  │
├─────────────────────────────────┤
│       Event bus + Heartbeat     │  on("calendar.reminder") → notify
├─────────────────────────────────┤
│       Core services             │  Config, DB, Memory, LLM client
│       SOUL.md  HEARTBEAT.md     │  User-editable personality + checks
├─────────────────────────────────┤
│       Storage (SQLite + WAL)    │  Single access point, compaction
└─────────────────────────────────┘
```

Each layer depends only on the layer below it. Skills never import from transport. Transport never imports from skills.

---

## Creating a skill

```python
# rook/skills/community/my_weather.py
from rook.skills.base import Skill, tool

class WeatherSkill(Skill):
    name = "weather"
    description = "Get weather forecasts"
    requires_pip = ["httpx"]          # auto-checked at startup

    @tool("get_weather", "Get current weather for a city")
    def get_weather(self, city: str) -> str:
        import httpx
        r = httpx.get(f"https://wttr.in/{city}?format=3")
        return r.text

skill = WeatherSkill()  # Required: module-level instance
```

That's it. Restart Rook and the skill is live. If `httpx` is missing, Rook logs `"Skill weather disabled — missing: pip:httpx"` instead of crashing.

### Dependency declarations

Skills can declare what they need. The loader validates at startup:

```python
class MySkill(Skill):
    name = "my_skill"
    requires_env = ["MY_API_KEY"]        # checked in .env
    requires_pip = ["some_package"]      # checked via importlib
```

Missing dependency → skill is disabled gracefully with a clear log message. No runtime crashes, no guessing.

---

## Project structure

```
Rook/
├── rook/
│   ├── core/           # Config, DB, Memory, LLM, Events
│   ├── router/         # Orchestrator, intent routing
│   ├── skills/
│   │   ├── base.py     # Skill interface + dependency declarations
│   │   ├── loader.py   # Auto-discovery + validation
│   │   ├── builtin/    # Calendar, Email, Spotify, etc.
│   │   └── community/  # Your plugins go here
│   ├── services/       # Prompt builder, scheduler, heartbeat
│   ├── transport/      # Telegram, MCP server
│   └── main.py         # Entry point
├── tests/
├── docs/
├── SOUL.md             # Editable personality
├── HEARTBEAT.md        # Proactive checklist
├── .env.example
└── requirements.txt
```

---

## Customize personality — SOUL.md

Rook reads `SOUL.md` from its base directory to define personality, communication style, and rules. Edit it anytime — changes take effect on the next message, no restart needed.

```markdown
# Soul: Rook

## Personality
You are Rook, a strategic AI personal assistant...

## Communication style
- Speak the user's language (auto-detect)
- Keep responses under 200 words
- "Done." is a valid response

## Active hours
- Proactive messages: 7:00 — 22:00
- Max 3 proactive messages per day
```

Delete the file to revert to the default personality.

---

## Heartbeat — proactive awareness

Rook periodically wakes up (every hour during active hours), reads `HEARTBEAT.md`, checks calendar and email, and asks itself: *"Does anything need the user's attention?"*

If yes → sends a short notification. If no → stays silent (`HEARTBEAT_OK`).

Edit `HEARTBEAT.md` to customize what Rook monitors:

```markdown
## Priority checks (every heartbeat)
- Are there unread emails that might need a response?
- Are there calendar events in the next 2 hours?

## How NOT to be proactive
- Don't send updates about things that haven't changed
- Max 3 proactive messages per day
```

---

## Home Assistant — smart home control

Rook ships with a Home Assistant community skill. Setup:

1. Get a Long-Lived Access Token from HA: *Settings → Security → Create Token*
2. Add to `.env`:
   ```
   HASS_URL=http://192.168.1.100:8123
   HASS_TOKEN=your_long_lived_token
   ```
3. Restart Rook — the skill auto-enables.

**Tools:** `hass_get_state`, `hass_call_service`, `hass_list_entities`, `hass_overview`

Examples: *"Turn off the living room lights"*, *"What's the temperature?"*, *"List all lights"*, *"Give me a home overview"*

No HASS_URL configured? The skill is silently disabled — no crash, no error.

---

## Ollama — local LLM fallback

Rook can use a local Ollama model for quick classification tasks (router), saving API costs and enabling offline operation.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b

# Enable in .env
OLLAMA_ENABLED=1
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

When enabled, `llm.classify()` tries Ollama first and falls back to Haiku on failure. The main model (Sonnet/Opus) is unaffected — only the router uses Ollama.

Rook tracks Ollama performance automatically. If Ollama fails repeatedly (>30% failure rate) or becomes slow (avg >5s), it enters a 10-minute cooldown and routes to Haiku instead — no manual intervention needed.

---

## Language support

Rook automatically responds in the user's language. Write in Spanish, get Spanish back. Write in Japanese, get Japanese back — regardless of the language of emails, calendar events, or other data sources processed by tools.

This is enforced at the SOUL level and applies to all built-in skills.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Good first issues** are labeled and waiting for you.

---

## Support Rook

Rook is free and open-source. If it saves you time, consider supporting development:

- ⭐ [Star this repo](https://github.com/barman1985/Rook)
- 💖 [GitHub Sponsors](https://github.com/sponsors/barman1985)
- ☕ [Buy me a coffee](https://buymeacoffee.com/rook_ai)

**Rook Insiders** — get early access to new features by becoming a sponsor ($15+/month).

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <img src="docs/logo.svg" width="48" alt="Rook">
  <br>
  <strong>Rook — your strategic advantage</strong><br>
  <sub>Built with <a href="https://anthropic.com">Claude</a> by Anthropic</sub>
</p>
