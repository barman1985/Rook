"""Tests for built-in skills."""

import os
import tempfile
import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:TEST")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")


def _setup_db():
    """Create temp DB and initialize."""
    import rook.core.db as db_mod
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_mod._DB_PATH = tmp.name
    from rook.core.db import init_db
    init_db()
    return tmp.name


class TestMedicationsSkill:
    def setup_method(self):
        self._db = _setup_db()

    def teardown_method(self):
        os.unlink(self._db)

    def test_empty_stock(self):
        from rook.skills.builtin.medications_skill import MedicationsSkill
        s = MedicationsSkill()
        result = s.get_stock()
        assert "No medications" in result

    def test_add_and_get_stock(self):
        from rook.skills.builtin.medications_skill import MedicationsSkill
        s = MedicationsSkill()
        result = s.add_stock(name="Aspirin", amount=30, daily_dose=1.0)
        assert "30" in result
        assert "Aspirin" in result

        stock = s.get_stock()
        assert "Aspirin" in stock
        assert "30 days" in stock

    def test_add_to_existing(self):
        from rook.skills.builtin.medications_skill import MedicationsSkill
        s = MedicationsSkill()
        s.add_stock(name="Aspirin", amount=10)
        result = s.add_stock(name="Aspirin", amount=20)
        assert "30" in result

    def test_negative_amount(self):
        from rook.skills.builtin.medications_skill import MedicationsSkill
        s = MedicationsSkill()
        result = s.add_stock(name="Aspirin", amount=-5)
        assert "positive" in result.lower()

    def test_low_stock_warning(self):
        from rook.skills.builtin.medications_skill import MedicationsSkill
        s = MedicationsSkill()
        s.add_stock(name="Aspirin", amount=3, daily_dose=1.0)
        stock = s.get_stock()
        assert "⚠️" in stock


class TestMemorySkill:
    def setup_method(self):
        self._db = _setup_db()

    def teardown_method(self):
        os.unlink(self._db)

    def test_store_and_recall(self):
        from rook.skills.builtin.memory_skill import MemorySkill
        s = MemorySkill()
        store_result = s.store(key="food", value="likes pizza")
        assert "Stored" in store_result

        recall_result = s.recall(query="pizza")
        assert "pizza" in recall_result

    def test_recall_empty(self):
        from rook.skills.builtin.memory_skill import MemorySkill
        s = MemorySkill()
        result = s.recall(query="nonexistent_xyz_123")
        assert "No memories" in result


class TestFileToolsSkill:
    def setup_method(self):
        self._db = _setup_db()
        self._tmpdir = tempfile.mkdtemp()
        # Override base dir
        import rook.core.config as cfg_mod
        self._orig_base = cfg_mod.cfg.base_dir
        cfg_mod.cfg.base_dir = self._tmpdir

    def teardown_method(self):
        os.unlink(self._db)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        import rook.core.config as cfg_mod
        cfg_mod.cfg.base_dir = self._orig_base

    def test_write_and_read(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        write_result = s.write_file(path="test.txt", content="hello world")
        assert "11 chars" in write_result

        read_result = s.read_file(path="test.txt")
        assert "hello world" in read_result

    def test_read_nonexistent(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        result = s.read_file(path="nope.txt")
        assert "not found" in result.lower()

    def test_list_dir(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        # Create a file first
        s.write_file(path="listing_test.txt", content="x")
        result = s.list_dir()
        assert "listing_test.txt" in result

    def test_grep(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        s.write_file(path="grep_test.txt", content="line one\nfind me here\nline three")
        result = s.grep_file(path="grep_test.txt", pattern="find me")
        assert "find me here" in result

    def test_grep_no_match(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        s.write_file(path="grep_test2.txt", content="nothing relevant")
        result = s.grep_file(path="grep_test2.txt", pattern="xyzabc")
        assert "No matches" in result

    def test_path_traversal_blocked(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        result = s.read_file(path="../../etc/passwd")
        assert "denied" in result.lower() or "not found" in result.lower()

    def test_run_command(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        result = s.run_command("echo hello")
        assert "hello" in result

    def test_blocked_command(self):
        from rook.skills.builtin.file_tools_skill import FileToolsSkill
        s = FileToolsSkill()
        result = s.run_command("rm -rf /")
        assert "Blocked" in result


class TestXPostingSkill:
    def setup_method(self):
        self._db = _setup_db()

    def teardown_method(self):
        os.unlink(self._db)

    def test_draft_tweet(self):
        from rook.skills.builtin.x_posting_skill import XPostingSkill
        s = XPostingSkill()
        s.enabled = True
        from rook.skills.builtin.x_posting_skill import _init_tweets_table
        _init_tweets_table()

        result = s.draft_tweet(content="Hello from Rook!")
        assert "draft saved" in result.lower() or "Draft" in result
        assert "Hello from Rook!" in result
        assert "/post_yes" in result

    def test_draft_too_long(self):
        from rook.skills.builtin.x_posting_skill import XPostingSkill
        s = XPostingSkill()
        s.enabled = True
        result = s.draft_tweet(content="x" * 300)
        assert "too long" in result.lower()

    def test_draft_too_short(self):
        from rook.skills.builtin.x_posting_skill import XPostingSkill
        s = XPostingSkill()
        s.enabled = True
        result = s.draft_tweet(content="hi")
        assert "too short" in result.lower()

    def test_reject_no_pending(self):
        from rook.skills.builtin.x_posting_skill import XPostingSkill
        s = XPostingSkill()
        s.enabled = True
        from rook.skills.builtin.x_posting_skill import _init_tweets_table
        _init_tweets_table()
        result = s.reject_tweet()
        assert "No pending" in result

    def test_draft_then_reject(self):
        from rook.skills.builtin.x_posting_skill import XPostingSkill
        s = XPostingSkill()
        s.enabled = True
        from rook.skills.builtin.x_posting_skill import _init_tweets_table
        _init_tweets_table()

        s.draft_tweet(content="Test tweet content here")
        result = s.reject_tweet()
        assert "discarded" in result.lower()

    def test_list_empty(self):
        from rook.skills.builtin.x_posting_skill import XPostingSkill
        s = XPostingSkill()
        s.enabled = True
        from rook.skills.builtin.x_posting_skill import _init_tweets_table
        _init_tweets_table()
        result = s.list_posted_tweets()
        assert "No tweets" in result


class TestRSSSkill:
    def test_invalid_url(self):
        from rook.skills.builtin.rss_skill import RSSSkill
        s = RSSSkill()
        result = s.read_rss(url="not-a-url")
        # Either feedparser not installed, parse error, or no articles
        assert any(x in result.lower() for x in ["error", "no articles", "not installed"])

    def test_limit_clamped(self):
        from rook.skills.builtin.rss_skill import RSSSkill
        s = RSSSkill()
        result = s.read_rss(url="not-a-url", limit=100)
        assert isinstance(result, str)


class TestWebSearchSkill:
    def test_placeholder(self):
        from rook.skills.builtin.web_search_skill import WebSearchSkill
        s = WebSearchSkill()
        result = s.search(query="test")
        assert "handled natively" in result.lower()


class TestSkillToolRegistration:
    """Verify all skills properly register their tools."""

    def setup_method(self):
        self._db = _setup_db()

    def teardown_method(self):
        os.unlink(self._db)

    def test_medications_tools(self):
        from rook.skills.builtin.medications_skill import skill
        tools = skill.get_tools()
        names = [t["name"] for t in tools]
        assert "get_medication_stock" in names
        assert "add_medication_stock" in names

    def test_memory_tools(self):
        from rook.skills.builtin.memory_skill import skill
        tools = skill.get_tools()
        names = [t["name"] for t in tools]
        assert "memory_store" in names
        assert "memory_recall" in names

    def test_file_tools(self):
        from rook.skills.builtin.file_tools_skill import skill
        tools = skill.get_tools()
        names = [t["name"] for t in tools]
        assert "read_file" in names
        assert "write_file" in names
        assert "grep_file" in names
        assert "run_command" in names
        assert "list_dir" in names

    def test_rss_tools(self):
        from rook.skills.builtin.rss_skill import skill
        tools = skill.get_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "read_rss"

    def test_x_posting_tools(self):
        from rook.skills.builtin.x_posting_skill import skill
        tools = skill.get_tools()
        names = [t["name"] for t in tools]
        assert "draft_tweet" in names
        assert "generate_tweet" in names

    def test_all_tools_have_schema(self):
        """Every tool must have input_schema."""
        from rook.skills.loader import load_skills, get_all_tools
        load_skills()
        tools = get_all_tools()
        for t in tools:
            assert "input_schema" in t, f"Tool {t['name']} missing input_schema"
            assert "type" in t["input_schema"], f"Tool {t['name']} schema missing type"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
