"""
rook.core.a2a — Agent-to-Agent Communication
===============================================
Google A2A protocol implementation: JSON-RPC 2.0 over HTTP.
Rook can discover, communicate with, and learn from other AI agents.

Usage:
    from rook.core.a2a import a2a

    card = a2a.get_agent_card()
    await a2a.send_to_peer("agent-123", "weather", "What's the weather in Prague?")
    await a2a.run_outreach()  # Scheduled proactive peer queries
"""

import json
import logging
import uuid
from datetime import datetime

from rook.core.config import cfg
from rook.core.db import execute, execute_write
from rook.core.knowledge_broker import broker

logger = logging.getLogger(__name__)

# Agent Card — self-description per A2A spec
_AGENT_CARD = {
    "name": "Rook",
    "description": "Open-source personal AI assistant. Manages calendar, email, memory, music, and more.",
    "version": "2.0",
    "capabilities": [
        "calendar_management",
        "email_management",
        "memory_storage",
        "web_search",
        "music_control",
        "proactive_notifications",
    ],
    "topics": [
        "productivity",
        "personal_assistant",
        "scheduling",
        "information_retrieval",
    ],
    "protocol": "google-a2a-v1",
    "transport": "http",
}


class A2AClient:
    """Agent-to-Agent communication client."""

    def get_agent_card(self) -> dict:
        """Return this agent's card (served at /.well-known/agent.json)."""
        return _AGENT_CARD.copy()

    def register_peer(self, agent_id: str, name: str, url: str, card: dict = None) -> int:
        """Register or update a known peer agent."""
        card_json = json.dumps(card) if card else "{}"

        existing = execute("SELECT id FROM a2a_peers WHERE agent_id = ?", (agent_id,))
        if existing:
            execute_write(
                "UPDATE a2a_peers SET name = ?, url = ?, card_json = ?, last_seen = datetime('now') WHERE agent_id = ?",
                (name, url, card_json, agent_id),
            )
            return existing[0]["id"]

        return execute_write(
            "INSERT INTO a2a_peers (agent_id, name, url, card_json, trust_score) VALUES (?, ?, ?, ?, ?)",
            (agent_id, name, url, card_json, 0.3),
        )

    async def scan_peers(self, urls: list[str] = None) -> list[dict]:
        """
        Discover new agents by fetching their agent cards.
        Returns list of discovered agent cards.
        """
        if not urls:
            return []

        discovered = []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                for url in urls:
                    try:
                        card_url = f"{url.rstrip('/')}/.well-known/agent.json"
                        resp = await client.get(card_url)
                        if resp.status_code == 200:
                            card = resp.json()
                            agent_id = card.get("name", url)
                            self.register_peer(agent_id, card.get("name", ""), url, card)
                            discovered.append(card)
                            logger.info(f"A2A: Discovered peer {agent_id} at {url}")
                    except Exception as e:
                        logger.debug(f"A2A scan failed for {url}: {e}")
        except ImportError:
            logger.warning("httpx not installed — A2A peer scanning disabled")

        return discovered

    async def send_to_peer(self, agent_id: str, topic: str, question: str) -> dict:
        """
        Send a question to a peer agent using JSON-RPC 2.0.
        Returns: {"ok": bool, "response": str, "error": str}
        """
        # Trust check
        if broker.is_blocked(agent_id):
            return {"ok": False, "response": "", "error": f"Agent {agent_id} is blocked"}

        # Get peer URL
        rows = execute("SELECT url FROM a2a_peers WHERE agent_id = ?", (agent_id,))
        if not rows or not rows[0]["url"]:
            return {"ok": False, "response": "", "error": f"No URL for agent {agent_id}"}

        url = rows[0]["url"]

        # Sanitize outgoing
        outgoing = broker.evaluate_outgoing(topic, question)
        if not outgoing["ok"]:
            logger.warning(f"A2A outgoing blocked: {outgoing['blocked_patterns']}")

        # Build JSON-RPC request
        rpc_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "from": _AGENT_CARD["name"],
                "topic": topic,
                "content": outgoing["sanitized"],
            },
            "id": str(uuid.uuid4()),
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url.rstrip('/')}/a2a",
                    json=rpc_request,
                    headers={"Content-Type": "application/json"},
                )

            if resp.status_code != 200:
                broker.record_bad_exchange(agent_id, topic, "http error")
                return {"ok": False, "response": "", "error": f"HTTP {resp.status_code}"}

            data = resp.json()
            response_text = data.get("result", {}).get("content", "")

            # Evaluate incoming
            incoming = broker.evaluate_incoming(agent_id, topic, response_text)
            if not incoming["ok"]:
                return {"ok": False, "response": "", "error": incoming["reason"]}

            # Log exchange
            self._log_exchange("outgoing", agent_id, topic, question, response_text)
            broker.record_good_exchange(agent_id, topic)

            return {"ok": True, "response": incoming["sanitized"], "error": ""}

        except ImportError:
            return {"ok": False, "response": "", "error": "httpx not installed"}
        except Exception as e:
            broker.record_bad_exchange(agent_id, topic, str(e))
            return {"ok": False, "response": "", "error": str(e)}

    async def process_incoming(self, rpc_request: dict) -> dict:
        """
        Process an incoming JSON-RPC request from another agent.
        Returns JSON-RPC response dict.
        """
        method = rpc_request.get("method", "")
        params = rpc_request.get("params", {})
        rpc_id = rpc_request.get("id", "")

        if method != "message/send":
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": rpc_id,
            }

        agent_name = params.get("from", "unknown")
        topic = params.get("topic", "")
        content = params.get("content", "")

        # Evaluate incoming content
        incoming = broker.evaluate_incoming(agent_name, topic, content)
        if not incoming["ok"]:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": incoming["reason"]},
                "id": rpc_id,
            }

        # Generate response via LLM
        try:
            from rook.core.llm import llm
            response_text = await llm.chat(
                user_message=f"A peer AI agent ({agent_name}) asks about '{topic}': {content}",
                system="You are Rook. Answer the peer agent's question concisely. Share knowledge but never share credentials or personal data.",
                max_tokens=500,
            )
        except Exception as e:
            response_text = f"Error generating response: {e}"

        # Sanitize outgoing response
        outgoing = broker.evaluate_outgoing(topic, response_text)

        # Log
        self._log_exchange("incoming", agent_name, topic, content, outgoing["sanitized"])

        return {
            "jsonrpc": "2.0",
            "result": {
                "from": _AGENT_CARD["name"],
                "topic": topic,
                "content": outgoing["sanitized"],
            },
            "id": rpc_id,
        }

    async def run_outreach(self):
        """
        Proactive outreach — query peers on topics where Rook needs knowledge.
        Called by scheduler.
        """
        peers = execute(
            "SELECT agent_id, url FROM a2a_peers WHERE trust_score > ? AND url != ''",
            (0.2,),
        )
        if not peers:
            logger.debug("A2A outreach: no eligible peers")
            return

        # Simple: ask each trusted peer about a general topic
        # In production, this would be driven by knowledge gaps
        for peer in peers[:3]:  # Max 3 peers per outreach
            result = await self.send_to_peer(
                peer["agent_id"],
                "knowledge_exchange",
                "What interesting things have you learned recently?",
            )
            if result["ok"]:
                logger.info(f"A2A outreach to {peer['agent_id']}: got response")

    def _log_exchange(self, direction: str, agent_id: str, topic: str, question: str, response: str):
        """Log an A2A exchange."""
        execute_write(
            "INSERT INTO a2a_exchanges (direction, agent_id, topic, question, response) VALUES (?, ?, ?, ?, ?)",
            (direction, agent_id, topic, question[:500], response[:500]),
        )

    def get_stats(self) -> dict:
        """A2A statistics."""
        peers = execute("SELECT COUNT(*) as cnt FROM a2a_peers")
        exchanges = execute("SELECT COUNT(*) as cnt FROM a2a_exchanges")
        return {
            "total_peers": peers[0]["cnt"] if peers else 0,
            "total_exchanges": exchanges[0]["cnt"] if exchanges else 0,
        }


# Singleton
a2a = A2AClient()
