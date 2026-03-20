"""
Built-in skill: Medication tracker
=====================================
Track medication stock, daily doses, low stock warnings.
"""

import logging

from rook.skills.base import Skill, tool
from rook.core.db import get_db, execute, execute_write

logger = logging.getLogger(__name__)


def _init_meds_table():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medications (
                name        TEXT PRIMARY KEY,
                stock       INTEGER DEFAULT 0,
                daily_dose  REAL DEFAULT 1.0,
                unit        TEXT DEFAULT 'pills',
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


class MedicationsSkill(Skill):
    name = "medications"
    description = "Track medication stock and daily doses"
    version = "1.0"

    def __init__(self):
        super().__init__()
        _init_meds_table()

    @tool(
        "get_medication_stock",
        "Show current medication stock and days remaining",
        {"type": "object", "properties": {}, "required": []}
    )
    def get_stock(self) -> str:
        rows = execute("SELECT * FROM medications ORDER BY name")
        if not rows:
            return "No medications tracked. Use add_medication_stock to add."

        lines = ["Medication stock:"]
        for r in rows:
            days_left = int(r["stock"] / r["daily_dose"]) if r["daily_dose"] > 0 else "∞"
            warning = " ⚠️" if isinstance(days_left, int) and days_left < 7 else ""
            lines.append(f"  • {r['name']}: {r['stock']} {r['unit']} ({days_left} days left){warning}")
        return "\n".join(lines)

    @tool(
        "add_medication_stock",
        "Add medication stock after pharmacy pickup",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Medication name"},
            "amount": {"type": "integer", "description": "Amount to add"},
            "daily_dose": {"type": "number", "description": "Daily dose (default 1.0, optional)"},
        }, "required": ["name", "amount"]}
    )
    def add_stock(self, name: str, amount: int, daily_dose: float = 1.0) -> str:
        if amount <= 0:
            return "Amount must be positive."

        existing = execute("SELECT * FROM medications WHERE name = ?", (name,))
        if existing:
            execute_write(
                "UPDATE medications SET stock = stock + ?, updated_at = datetime('now') WHERE name = ?",
                (amount, name)
            )
            new_stock = existing[0]["stock"] + amount
        else:
            execute_write(
                "INSERT INTO medications (name, stock, daily_dose) VALUES (?, ?, ?)",
                (name, amount, daily_dose)
            )
            new_stock = amount

        return f"Added {amount} to {name}. Current stock: {new_stock}"


skill = MedicationsSkill()
