"""
rook.skills.loader — Skill auto-discovery and management
==========================================================
Scans builtin/ and community/ directories for skills.
Each skill module must export a `skill` instance.

Usage:
    from rook.skills.loader import load_skills, get_all_tools, execute_tool

    skills = load_skills()
    tools = get_all_tools()         # Anthropic tool definitions
    result = await execute_tool("get_weather", {"city": "Prague"})
"""

import asyncio
import importlib
import logging
from pathlib import Path
from typing import Any

from rook.skills.base import Skill

logger = logging.getLogger(__name__)

_loaded_skills: dict[str, Skill] = {}
_tool_handlers: dict[str, Any] = {}
_all_tools: list[dict] = []


def load_skills() -> dict[str, Skill]:
    """Discover and load all skills from builtin/ and community/ dirs."""
    global _loaded_skills, _tool_handlers, _all_tools

    _loaded_skills = {}
    _tool_handlers = {}
    _all_tools = []

    skills_dir = Path(__file__).parent
    dirs = [skills_dir / "builtin", skills_dir / "community"]

    for skill_dir in dirs:
        if not skill_dir.exists():
            continue
        for py_file in sorted(skill_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            _load_skill_module(py_file, skill_dir.name)

    logger.info(f"Loaded {len(_loaded_skills)} skills, {len(_all_tools)} tools")
    return _loaded_skills


def _load_skill_module(path: Path, category: str):
    """Load a single skill module."""
    module_name = path.stem
    try:
        # Import relative to skills package
        if category == "builtin":
            mod = importlib.import_module(f"rook.skills.builtin.{module_name}")
        else:
            # Community skills: load by file path
            spec = importlib.util.spec_from_file_location(f"rook.skills.community.{module_name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

        # Module must export `skill` instance
        skill = getattr(mod, "skill", None)
        if not isinstance(skill, Skill):
            logger.debug(f"Skipping {path.name}: no `skill` instance")
            return

        if not skill.enabled:
            logger.debug(f"Skipping disabled skill: {skill.name}")
            return

        # Check dependencies
        deps_ok, deps_missing = skill.check_dependencies()
        if not deps_ok:
            logger.warning(f"Skill {skill.name} disabled — missing: {', '.join(deps_missing)}")
            return

        _loaded_skills[skill.name] = skill

        # Register tools
        for tool_def in skill.get_tools():
            _all_tools.append(tool_def)
        for tool_name, handler in skill.get_tool_handlers().items():
            _tool_handlers[tool_name] = handler

        logger.debug(f"Loaded skill: {skill.name} ({category}, {len(skill.get_tools())} tools)")

    except Exception as e:
        logger.warning(f"Failed to load skill {path.name}: {e}")


def get_all_tools() -> list[dict]:
    """Return all Anthropic-compatible tool definitions."""
    return _all_tools


def get_all_skills() -> dict[str, Skill]:
    """Return loaded skills."""
    return _loaded_skills


async def execute_tool(name: str, inputs: dict) -> str:
    """Execute a tool by name. Returns result string."""
    handler = _tool_handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"

    try:
        if asyncio.iscoroutinefunction(handler):
            result = await handler(**inputs)
        else:
            result = handler(**inputs)
        return str(result) if result is not None else "OK"
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return f"Error: {e}"
