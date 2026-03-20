"""Tests for Rook core modules."""

import os
import sys
import pytest
import asyncio

# Set dummy env vars before importing
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:TEST")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")


class TestConfig:
    def test_from_env(self):
        from rook.core.config import Config
        c = Config(
            anthropic_api_key="test",
            telegram_bot_token="123:TEST",
            telegram_chat_id="12345",
        )
        assert c.anthropic_api_key == "test"
        assert c.google_enabled is False
        assert c.spotify_enabled is False

    def test_validate_missing(self):
        from rook.core.config import Config
        c = Config()
        errors = c.validate()
        assert "ANTHROPIC_API_KEY" in errors
        assert "TELEGRAM_BOT_TOKEN" in errors

    def test_validate_complete(self):
        from rook.core.config import Config
        c = Config(
            anthropic_api_key="key",
            telegram_bot_token="tok",
            telegram_chat_id="123",
        )
        assert c.validate() == []

    def test_feature_flags(self):
        from rook.core.config import Config
        c = Config(
            spotify_client_id="id",
            spotify_client_secret="secret",
        )
        assert c.spotify_enabled is True
        assert c.google_enabled is False


class TestDB:
    def setup_method(self):
        """Use temp file DB for tests."""
        import tempfile
        import rook.core.db as db_mod
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_mod._DB_PATH = self._tmp.name
        from rook.core.db import init_db
        init_db()

    def teardown_method(self):
        import os
        os.unlink(self._tmp.name)

    def test_init_creates_tables(self):
        from rook.core.db import execute
        rows = execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = [r["name"] for r in rows]
        assert "messages" in names
        assert "memory" in names
        assert "user_profile" in names

    def test_execute_write_and_read(self):
        from rook.core.db import execute, execute_write
        rid = execute_write("INSERT INTO messages (role, content) VALUES (?, ?)", ("user", "hello"))
        assert rid > 0
        rows = execute("SELECT * FROM messages WHERE role = ?", ("user",))
        assert len(rows) == 1
        assert rows[0]["content"] == "hello"


class TestEventBus:
    def test_sync_handler(self):
        from rook.core.events import EventBus
        bus = EventBus()
        results = []

        @bus.on("test.event")
        def handler(data):
            results.append(data)

        asyncio.get_event_loop().run_until_complete(bus.emit("test.event", {"msg": "hi"}))
        assert len(results) == 1
        assert results[0]["msg"] == "hi"

    def test_async_handler(self):
        from rook.core.events import EventBus
        bus = EventBus()
        results = []

        @bus.on("test.async")
        async def handler(data):
            results.append(data)

        asyncio.get_event_loop().run_until_complete(bus.emit("test.async", "ok"))
        assert results == ["ok"]

    def test_wildcard(self):
        from rook.core.events import EventBus
        bus = EventBus()
        results = []

        @bus.on("calendar.*")
        def handler(data):
            results.append(data)

        asyncio.get_event_loop().run_until_complete(bus.emit("calendar.reminder", "hey"))
        assert len(results) == 1

    def test_no_handlers(self):
        from rook.core.events import EventBus
        bus = EventBus()
        # Should not raise
        asyncio.get_event_loop().run_until_complete(bus.emit("nothing", None))


class TestMemory:
    def setup_method(self):
        import tempfile
        import rook.core.db as db_mod
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_mod._DB_PATH = self._tmp.name
        from rook.core.db import init_db
        init_db()

    def teardown_method(self):
        import os
        os.unlink(self._tmp.name)

    def test_store_and_recall(self):
        from rook.core.memory import Memory
        mem = Memory()
        mem.store("pref", "likes jazz", source="test")
        results = mem.recall("jazz")
        assert len(results) >= 1
        assert "jazz" in results[0]["value"]

    def test_recall_empty(self):
        from rook.core.memory import Memory
        mem = Memory()
        results = mem.recall("nonexistent_query_xyz")
        assert results == []

    def test_activation_increases_with_access(self):
        from rook.core.memory import Memory
        mem = Memory()
        mem.store("test", "value", source="test")
        r1 = mem.recall("test")
        r2 = mem.recall("test")
        # Second recall should have higher access count
        assert r2[0]["access_count"] >= r1[0]["access_count"]


class TestSkillBase:
    def test_tool_decorator(self):
        from rook.skills.base import Skill, tool

        class TestSkill(Skill):
            name = "test"

            @tool("do_thing", "Does a thing")
            def do_thing(self, x: str) -> str:
                return f"did {x}"

        s = TestSkill()
        tools = s.get_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "do_thing"

        handlers = s.get_tool_handlers()
        assert "do_thing" in handlers
        assert handlers["do_thing"](x="it") == "did it"

    def test_schema_inference(self):
        from rook.skills.base import Skill, tool

        class TestSkill(Skill):
            name = "test"

            @tool("calc", "Calculate")
            def calc(self, a: int, b: str = "default") -> str:
                return ""

        s = TestSkill()
        schema = s.get_tools()[0]["input_schema"]
        assert schema["properties"]["a"]["type"] == "integer"
        assert schema["properties"]["b"]["type"] == "string"
        assert "a" in schema["required"]
        assert "b" not in schema["required"]


class TestSkillLoader:
    def test_load_builtin_skills(self):
        import tempfile
        import rook.core.db as db_mod
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_mod._DB_PATH = tmp.name
        from rook.core.db import init_db
        init_db()

        from rook.skills.loader import load_skills, get_all_tools
        skills = load_skills()
        tools = get_all_tools()

        # At minimum memory and rss should load (no external deps)
        assert "memory" in skills
        assert "rss" in skills
        assert len(tools) >= 3

        import os
        os.unlink(tmp.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
