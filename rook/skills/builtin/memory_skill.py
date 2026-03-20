"""
Built-in skill: Memory
========================
Store and recall facts using ACT-R memory.
"""

from rook.skills.base import Skill, tool
from rook.core.memory import memory


class MemorySkill(Skill):
    name = "memory"
    description = "Store and recall facts with ACT-R activation scoring"
    version = "1.0"

    @tool(
        "memory_store",
        "Store a fact or preference for later recall",
        {"type": "object", "properties": {
            "key": {"type": "string", "description": "Category or topic"},
            "value": {"type": "string", "description": "The fact to remember"},
        }, "required": ["key", "value"]}
    )
    def store(self, key: str, value: str) -> str:
        memory.store(key, value, source="conversation")
        return f"Stored: {key} = {value}"

    @tool(
        "memory_recall",
        "Recall stored facts matching a query",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for"},
        }, "required": ["query"]}
    )
    def recall(self, query: str) -> str:
        results = memory.recall(query, limit=5)
        if not results:
            return "No memories found."
        lines = []
        for r in results:
            lines.append(f"- {r['key']}: {r['value']} (activation: {r['activation']:.2f})")
        return "\n".join(lines)


skill = MemorySkill()
