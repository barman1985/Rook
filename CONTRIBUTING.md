# Contributing to Rook

Thanks for your interest in making Rook better! Here's how to get started.

## Quick start

```bash
git clone https://github.com/barman1985/Rook.git
cd Rook
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys
python -m rook.main
```

## Ways to contribute

### Create a skill
The easiest way to contribute. Drop a Python file in `rook/skills/community/`:

```python
from rook.skills.base import Skill, tool

class MySkill(Skill):
    name = "my_skill"
    description = "What it does"

    @tool("tool_name", "Tool description")
    def my_tool(self, param: str) -> str:
        return "result"

skill = MySkill()
```

### Report bugs
Open an issue with:
- What you expected
- What happened
- Steps to reproduce
- Your Python version and OS

### Submit a PR
1. Fork the repo
2. Create a branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `python -m pytest tests/`
5. Push and open a PR

## Code style

- Python 3.11+ features are welcome
- Type hints on public functions
- Docstrings on modules and classes
- No direct `sqlite3.connect()` — use `rook.core.db`
- No direct `.env` reading — use `rook.core.config.cfg`
- Skills import from `rook.core` and `rook.skills.base` only

## Architecture rules

- Each layer depends only on the layer below it
- Skills never import from transport
- Transport never imports from skills
- All DB access through `rook.core.db`
- All config through `rook.core.config`
- All LLM calls through `rook.core.llm`

## Questions?

Open a GitHub Discussion or reach out on our community chat.
