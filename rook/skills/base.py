"""
rook.skills.base — Skill interface
====================================
Every skill (built-in or community) implements this interface.
Drop a .py file in skills/community/ and it's auto-discovered.

Creating a skill:
    from rook.skills.base import Skill, tool

    class WeatherSkill(Skill):
        name = "weather"
        description = "Get weather forecasts"
        version = "1.0"

        @tool("get_weather", "Get current weather for a city")
        async def get_weather(self, city: str) -> str:
            return f"Weather in {city}: sunny, 22C"

    skill = WeatherSkill()  # Required: module-level instance
"""

import logging
from abc import ABC
from typing import Any

logger = logging.getLogger(__name__)


def tool(name: str, description: str, parameters: dict = None):
    """Decorator to mark a method as an LLM-callable tool."""
    def decorator(func):
        func._tool_meta = {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
        return func
    return decorator


class Skill(ABC):
    """Base class for all Rook skills."""

    name: str = "unnamed"
    description: str = ""
    version: str = "1.0"
    enabled: bool = True

    def get_tools(self) -> list[dict]:
        """Return Anthropic-compatible tool definitions."""
        tools = []
        for method_name in dir(self):
            method = getattr(self, method_name, None)
            if callable(method) and hasattr(method, "_tool_meta"):
                meta = method._tool_meta
                tool_def = {
                    "name": meta["name"],
                    "description": meta["description"],
                    "input_schema": meta.get("parameters") or self._infer_schema(method),
                }
                tools.append(tool_def)
        return tools

    def get_tool_handlers(self) -> dict:
        """Return {tool_name: handler_method} mapping."""
        handlers = {}
        for method_name in dir(self):
            method = getattr(self, method_name, None)
            if callable(method) and hasattr(method, "_tool_meta"):
                handlers[method._tool_meta["name"]] = method
        return handlers

    def _infer_schema(self, method) -> dict:
        """Infer JSON schema from type hints."""
        import inspect
        sig = inspect.signature(method)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            prop = {"type": "string"}
            if param.annotation != inspect.Parameter.empty:
                type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
                prop["type"] = type_map.get(param.annotation, "string")
            properties[param_name] = prop
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def on_load(self):
        """Called when skill is loaded. Override for initialization."""
        pass

    async def on_unload(self):
        """Called when skill is unloaded. Override for cleanup."""
        pass

    def __repr__(self):
        return f"<Skill {self.name} v{self.version}>"
