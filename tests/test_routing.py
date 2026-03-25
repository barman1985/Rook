# tests/test_routing.py
# Unit testy pro orchestrator history handling a LLM Ollama metrics
# Spuštění: cd /opt/rook && python3 -m pytest tests/test_routing.py -v

import sys
import time
import pytest
import asyncio
from pathlib import Path
from collections import deque
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# _OllamaMetrics — testujeme logiku inline bez importu llm.py/anthropic
# (lekce z Jarvise: extrahovat čistou logiku aby se vyhnulo závislosti)
# ═══════════════════════════════════════════════════════════════════

class _OllamaMetricsTestable:
    """Kopie _OllamaMetrics logiky z llm.py — bez závislosti na anthropic."""
    def __init__(self, window_size=10, cooldown_secs=600):
        self.window_size = window_size
        self.cooldown_secs = cooldown_secs
        self.call_times: deque = deque(maxlen=window_size)
        self.results: deque = deque(maxlen=window_size)
        self._cooldown_until = 0.0

    def record_success(self, duration: float):
        self.call_times.append(duration)
        self.results.append(True)

    def record_failure(self, duration: float):
        self.call_times.append(duration)
        self.results.append(False)
        if len(self.results) >= 3:
            fail_rate = sum(1 for r in self.results if not r) / len(self.results)
            if fail_rate > 0.3:
                self._cooldown_until = time.time() + self.cooldown_secs

    def should_use(self) -> bool:
        if time.time() < self._cooldown_until:
            return False
        if len(self.call_times) >= 3:
            avg = sum(self.call_times) / len(self.call_times)
            if avg > 5.0:
                self._cooldown_until = time.time() + self.cooldown_secs
                return False
        return True


class TestOllamaMetrics:

    def setup_method(self):
        self.Metrics = _OllamaMetricsTestable

    def test_should_use_initially_true(self):
        """Nové metrics → should_use() = True."""
        m = self.Metrics()
        assert m.should_use() is True

    def test_success_records_correctly(self):
        """record_success() přidá čas a True."""
        m = self.Metrics()
        m.record_success(0.5)
        assert len(m.call_times) == 1
        assert m.results[-1] is True

    def test_failure_records_correctly(self):
        """record_failure() přidá čas a False."""
        m = self.Metrics()
        m.record_failure(1.0)
        assert len(m.call_times) == 1
        assert m.results[-1] is False

    def test_cooldown_after_high_fail_rate(self):
        """40% selhání z 10 → cooldown."""
        m = self.Metrics(window_size=10, cooldown_secs=600)
        for _ in range(6):
            m.record_success(0.3)
        for _ in range(4):
            m.record_failure(1.0)
        assert m.should_use() is False

    def test_no_cooldown_below_threshold(self):
        """20% selhání z 10 → žádný cooldown."""
        m = self.Metrics(window_size=10, cooldown_secs=600)
        for _ in range(8):
            m.record_success(0.3)
        for _ in range(2):
            m.record_failure(1.0)
        assert m.should_use() is True

    def test_cooldown_on_high_latency(self):
        """Průměr >5s z 5 vzorků → cooldown."""
        m = self.Metrics(window_size=5, cooldown_secs=600)
        for _ in range(5):
            m.record_success(6.0)
        assert m.should_use() is False

    def test_no_cooldown_fast_responses(self):
        """Průměr <5s → žádný cooldown."""
        m = self.Metrics(window_size=5, cooldown_secs=600)
        for _ in range(5):
            m.record_success(0.2)
        assert m.should_use() is True

    def test_cooldown_triggers_on_3_consecutive_failures(self):
        """3 selhání ze 3 = 100% > 30% → cooldown."""
        m = self.Metrics(window_size=10, cooldown_secs=600)
        for _ in range(3):
            m.record_failure(1.0)
        assert m.should_use() is False

    def test_window_size_respected(self):
        """deque maxlen omezuje počet vzorků."""
        m = self.Metrics(window_size=5, cooldown_secs=1)
        for _ in range(10):
            m.record_success(0.1)
        assert len(m.call_times) == 5


# ═══════════════════════════════════════════════════════════════════
# orchestrator.handle() — history parametr
# (lekce z Jarvise: pytest.importorskip pro moduly závisející na anthropic)
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorHistory:

    def setup_method(self):
        pytest.importorskip("anthropic", reason="anthropic not installed")

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_max_iterations_default_is_12(self):
        """Výchozí MAX_ITERATIONS = 12."""
        from rook.router.orchestrator import MAX_ITERATIONS
        assert MAX_ITERATIONS == 12

    def test_handle_without_history_uses_single_message(self):
        """Bez history → messages obsahuje jen aktuální zprávu."""
        from rook.router.orchestrator import handle

        captured = []

        async def mock_chat(messages, tools, system, model):
            captured.extend(messages)
            block = MagicMock()
            block.type = "text"
            block.text = "OK"
            response = MagicMock()
            response.content = [block]
            return response

        with patch("rook.router.orchestrator.llm.chat_with_tools", side_effect=mock_chat), \
             patch("rook.router.orchestrator.get_all_tools", return_value=[]):
            self._run(handle("Ahoj", "system"))

        assert len(captured) == 1
        assert captured[0] == {"role": "user", "content": "Ahoj"}

    def test_handle_with_history_prepends_context(self):
        """S history → starší zprávy jsou před aktuální zprávou."""
        from rook.router.orchestrator import handle

        captured = []

        async def mock_chat(messages, tools, system, model):
            captured.extend(messages)
            block = MagicMock()
            block.type = "text"
            block.text = "OK"
            response = MagicMock()
            response.content = [block]
            return response

        history = [
            {"role": "user",      "content": "první zpráva"},
            {"role": "assistant", "content": "první odpověď"},
            {"role": "user",      "content": "druhá zpráva"},
        ]

        with patch("rook.router.orchestrator.llm.chat_with_tools", side_effect=mock_chat), \
             patch("rook.router.orchestrator.get_all_tools", return_value=[]):
            self._run(handle("druhá zpráva", "system", history=history))

        # history[:-1] = první 2 zprávy + aktuální = celkem 3
        assert len(captured) == 3
        assert captured[0]["content"] == "první zpráva"
        assert captured[1]["content"] == "první odpověď"
        assert captured[2]["content"] == "druhá zpráva"

    def test_handle_with_single_message_history(self):
        """history s 1 zprávou → history[:-1] = [] → jen aktuální zpráva."""
        from rook.router.orchestrator import handle

        captured = []

        async def mock_chat(messages, tools, system, model):
            captured.extend(messages)
            block = MagicMock()
            block.type = "text"
            block.text = "OK"
            response = MagicMock()
            response.content = [block]
            return response

        history = [{"role": "user", "content": "jen tato zpráva"}]

        with patch("rook.router.orchestrator.llm.chat_with_tools", side_effect=mock_chat), \
             patch("rook.router.orchestrator.get_all_tools", return_value=[]):
            self._run(handle("jen tato zpráva", "system", history=history))

        assert len(captured) == 1
        assert captured[0]["content"] == "jen tato zpráva"


# ═══════════════════════════════════════════════════════════════════
# SOUL.md — jazykové pravidlo a anti-komentář pravidlo
# ═══════════════════════════════════════════════════════════════════

class TestSoulMd:

    def setup_method(self):
        soul_path = Path(__file__).parent.parent / "SOUL.md"
        self.soul = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""

    def test_language_rule_present(self):
        """SOUL.md obsahuje explicitní jazykové pravidlo."""
        assert "Always respond in the same language" in self.soul

    def test_language_rule_covers_tool_results(self):
        """Jazykové pravidlo zmiňuje tool results jako výjimku."""
        assert "tool results" in self.soul or "regardless of the language" in self.soul

    def test_no_commentary_rule_present(self):
        """SOUL.md obsahuje pravidlo proti nevyžádaným komentářům."""
        assert "side effect" in self.soul or "side-effect" in self.soul
