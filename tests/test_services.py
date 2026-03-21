"""Tests for services and transport."""

import os
import json
import tempfile
import asyncio
import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:TEST")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")


def _setup_db():
    import rook.core.db as db_mod
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_mod._DB_PATH = tmp.name
    from rook.core.db import init_db
    init_db()
    return tmp.name


class TestPromptService:
    def setup_method(self):
        self._db = _setup_db()

    def teardown_method(self):
        os.unlink(self._db)

    def test_build_system_prompt(self):
        from rook.skills.loader import load_skills
        load_skills()
        from rook.services.prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Rook" in prompt
        assert "Current time" in prompt
        assert "Active skills" in prompt

    def test_prompt_contains_timezone(self):
        from rook.skills.loader import load_skills
        load_skills()
        from rook.services.prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Europe/Prague" in prompt

    def test_prompt_contains_skills(self):
        from rook.skills.loader import load_skills
        load_skills()
        from rook.services.prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "memory" in prompt
        assert "rss" in prompt


class TestScheduler:
    def test_start_scheduler_in_loop(self):
        """Scheduler must start inside a running event loop."""
        pytest.importorskip("pytz")
        pytest.importorskip("apscheduler")
        from rook.services.scheduler import start_scheduler

        async def _test():
            start_scheduler()
            from rook.services.scheduler import _scheduler
            assert _scheduler is not None
            assert _scheduler.running
            _scheduler.shutdown(wait=False)

        asyncio.run(_test())

    def test_scheduler_has_jobs(self):
        pytest.importorskip("pytz")
        pytest.importorskip("apscheduler")
        from rook.services.scheduler import start_scheduler

        async def _test():
            start_scheduler()
            from rook.services.scheduler import _scheduler
            jobs = _scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            assert "morning_briefing" in job_ids
            assert "evening_summary" in job_ids
            assert "calendar_reminders" in job_ids
            _scheduler.shutdown(wait=False)

        asyncio.run(_test())


class TestNotifications:
    def test_handler_registered(self):
        """notification.send handler should be registered on import."""
        pytest.importorskip("httpx")
        from rook.core.events import bus
        import rook.services.notifications  # noqa: F401
        events = bus.list_events()
        assert "notification.send" in events


class TestMCPServer:
    def test_initialize(self):
        from rook.transport.mcp import handle_request
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = asyncio.run(handle_request(request))
        assert response["id"] == 1
        assert "protocolVersion" in response["result"]
        assert response["result"]["serverInfo"]["name"] == "rook"

    def test_tools_list(self):
        self._db = _setup_db()
        from rook.skills.loader import load_skills
        load_skills()
        from rook.transport.mcp import handle_request
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        response = asyncio.run(handle_request(request))
        tools = response["result"]["tools"]
        assert len(tools) > 0
        # Every tool has name, description, inputSchema
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t
        os.unlink(self._db)

    def test_tools_call(self):
        self._db = _setup_db()
        from rook.skills.loader import load_skills
        load_skills()
        from rook.transport.mcp import handle_request
        request = {
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": "memory_recall", "arguments": {"query": "test"}}
        }
        response = asyncio.run(handle_request(request))
        assert "content" in response["result"]
        assert response["result"]["content"][0]["type"] == "text"
        os.unlink(self._db)

    def test_tools_call_unknown(self):
        self._db = _setup_db()
        from rook.skills.loader import load_skills
        load_skills()
        from rook.transport.mcp import handle_request
        request = {
            "jsonrpc": "2.0", "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        }
        response = asyncio.run(handle_request(request))
        assert "Unknown tool" in response["result"]["content"][0]["text"]
        os.unlink(self._db)

    def test_unknown_method(self):
        from rook.transport.mcp import handle_request
        request = {"jsonrpc": "2.0", "id": 5, "method": "foo/bar", "params": {}}
        response = asyncio.run(handle_request(request))
        assert "error" in response
        assert response["error"]["code"] == -32601

    def test_notification_no_response(self):
        from rook.transport.mcp import handle_request
        request = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        response = asyncio.run(handle_request(request))
        assert response is None

    def test_prompts_list(self):
        from rook.transport.mcp import handle_request
        request = {"jsonrpc": "2.0", "id": 6, "method": "prompts/list", "params": {}}
        response = asyncio.run(handle_request(request))
        assert response["result"]["prompts"] == []

    def test_resources_list(self):
        from rook.transport.mcp import handle_request
        request = {"jsonrpc": "2.0", "id": 7, "method": "resources/list", "params": {}}
        response = asyncio.run(handle_request(request))
        assert response["result"]["resources"] == []


class TestSkillLoader:
    """Extended loader tests."""

    def setup_method(self):
        self._db = _setup_db()

    def teardown_method(self):
        os.unlink(self._db)

    def test_disabled_skills_not_loaded(self):
        """Skills with enabled=False should not appear."""
        from rook.skills.loader import load_skills
        skills = load_skills()
        for name, skill in skills.items():
            assert skill.enabled, f"Disabled skill {name} was loaded"

    def test_tool_handlers_callable(self):
        """Every registered handler must be callable."""
        from rook.skills.loader import load_skills, get_all_tools
        from rook.skills.loader import _tool_handlers
        load_skills()
        for name, handler in _tool_handlers.items():
            assert callable(handler), f"Handler {name} is not callable"

    def test_no_duplicate_tool_names(self):
        """Tool names must be unique across all skills."""
        from rook.skills.loader import load_skills, get_all_tools
        load_skills()
        tools = get_all_tools()
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names)), f"Duplicate tools: {[n for n in names if names.count(n) > 1]}"

    def test_execute_tool_memory_store(self):
        from rook.skills.loader import load_skills, execute_tool
        load_skills()
        result = asyncio.run(execute_tool("memory_store", {"key": "test", "value": "hello"}))
        assert "Stored" in result

    def test_execute_tool_unknown(self):
        from rook.skills.loader import load_skills, execute_tool
        load_skills()
        result = asyncio.run(execute_tool("fake_tool_xyz", {}))
        assert "Unknown tool" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
