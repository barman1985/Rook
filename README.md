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

- **Actually does things** — not a chatbot. Rook creates calendar events, sends emails, controls Spotify, and more.
- **Proactive, not reactive** — morning briefings, calendar reminders, follow-up detection.
- **Memory that works like yours** — ACT-R cognitive architecture: frequently accessed memories stay sharp, unused ones fade naturally.
- **Local voice** — speech-to-text and text-to-speech run locally on your machine. Free, private, no API costs.
- **Plugin system** — drop a Python file in `skills/community/` and Rook picks it up. No core changes needed.
- **Telegram-native** — zero onboarding. No new app to install.

---

## Features

| Feature | Description |
|---------|-------------|
| 📅 **Calendar** | Create, edit, delete, search events (Google Calendar) |
| 📧 **Email** | Read, search, send emails (Gmail) |
| 🎵 **Spotify** | Play, search, playlists, device control |
| 📺 **TV** | Power, apps, volume (Chromecast) |
| 🧠 **Memory** | ACT-R activation scoring, decay, long-term recall |
| 🔔 **Proactive** | Calendar reminders, morning briefings, evening summaries |
| 🎙️ **Voice** | Local STT (faster-whisper) + TTS (Piper) |
| 🌐 **Web search** | Current info via Anthropic web search |
| 🔌 **MCP Server** | Expose all tools to Claude Desktop, Cursor, etc. |
| 🧩 **Plugins** | Community-contributed skills, auto-discovered |

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
├─────────────────────────────────┤
│       Skill layer (pluggable)   │  Calendar, Email, Spotify, ...
│  ┌──────┐ ┌──────┐ ┌────────┐  │
│  │built │ │built │ │community│  │  Drop a .py, done.
│  │ -in  │ │ -in  │ │ plugin │  │
│  └──────┘ └──────┘ └────────┘  │
├─────────────────────────────────┤
│       Event bus                 │  on("calendar.reminder") → notify
├─────────────────────────────────┤
│       Core services             │  Config, DB, Memory, LLM client
├─────────────────────────────────┤
│       Storage (SQLite)          │  Single access point
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

    @tool("get_weather", "Get current weather for a city")
    def get_weather(self, city: str) -> str:
        import httpx
        r = httpx.get(f"https://wttr.in/{city}?format=3")
        return r.text

skill = WeatherSkill()  # Required: module-level instance
```

That's it. Restart Rook and the skill is live.

---

## Project structure

```
Rook/
├── rook/
│   ├── core/           # Config, DB, Memory, LLM, Events
│   ├── router/         # Orchestrator, intent routing
│   ├── skills/
│   │   ├── base.py     # Skill interface
│   │   ├── loader.py   # Auto-discovery
│   │   ├── builtin/    # Calendar, Email, Spotify, etc.
│   │   └── community/  # Your plugins go here
│   ├── services/       # Prompt builder, scheduler, briefings
│   ├── transport/      # Telegram, MCP server
│   └── main.py         # Entry point
├── tests/
├── docs/
├── .env.example
└── requirements.txt
```

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
