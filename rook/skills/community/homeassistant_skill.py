"""
Community skill: Home Assistant
=================================
Control your smart home via Home Assistant REST API.

Setup:
    1. Get a Long-Lived Access Token from HA:
       Settings → Security → Long-Lived Access Tokens → Create Token
    2. Add to .env:
       HASS_URL=http://192.168.1.100:8123
       HASS_TOKEN=your_long_lived_token

Tools:
    - hass_get_state: Get the state of any entity
    - hass_call_service: Call any HA service (turn on/off, set temp, etc.)
    - hass_list_entities: List entities by domain (light, switch, climate, etc.)
    - hass_overview: Get a quick overview of your home

Example:
    "Turn off the living room lights" → hass_call_service
    "What's the temperature?" → hass_get_state
    "List all lights" → hass_list_entities
"""

import os
import logging

import httpx

from rook.skills.base import Skill, tool

logger = logging.getLogger(__name__)


def _get_config() -> tuple[str, str]:
    """Get HA URL and token from environment."""
    url = os.environ.get("HASS_URL", "")
    token = os.environ.get("HASS_TOKEN", "")
    # Also try .env file
    if not url or not token:
        from rook.core.config import cfg
        from pathlib import Path
        env_path = Path(cfg.base_dir) / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("HASS_URL="):
                    url = url or line.partition("=")[2].strip()
                elif line.startswith("HASS_TOKEN="):
                    token = token or line.partition("=")[2].strip()
    return url.rstrip("/"), token


def _headers() -> dict:
    """Build auth headers."""
    _, token = _get_config()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _api_url(path: str) -> str:
    """Build full API URL."""
    url, _ = _get_config()
    return f"{url}/api/{path.lstrip('/')}"


class HomeAssistantSkill(Skill):
    name = "homeassistant"
    description = "Control smart home devices via Home Assistant"
    version = "1.0"
    requires_env = ["HASS_URL", "HASS_TOKEN"]

    @tool("hass_get_state", "Get the current state of a Home Assistant entity (e.g. light.living_room, sensor.temperature)")
    def get_state(self, entity_id: str) -> str:
        try:
            resp = httpx.get(
                _api_url(f"states/{entity_id}"),
                headers=_headers(),
                timeout=10,
            )
            if resp.status_code == 404:
                return f"Entity '{entity_id}' not found"
            resp.raise_for_status()
            data = resp.json()
            state = data.get("state", "unknown")
            attrs = data.get("attributes", {})
            friendly = attrs.get("friendly_name", entity_id)

            # Build useful info from attributes
            info = [f"{friendly}: {state}"]
            if "unit_of_measurement" in attrs:
                info[0] = f"{friendly}: {state} {attrs['unit_of_measurement']}"
            if "temperature" in attrs:
                info.append(f"  Temperature: {attrs['temperature']}°")
            if "brightness" in attrs:
                pct = round(attrs["brightness"] / 255 * 100)
                info.append(f"  Brightness: {pct}%")
            if "current_temperature" in attrs:
                info.append(f"  Current temp: {attrs['current_temperature']}°")

            return "\n".join(info)
        except Exception as e:
            return f"Error getting state of {entity_id}: {e}"

    @tool("hass_call_service", "Call a Home Assistant service. domain: light/switch/climate/etc. service: turn_on/turn_off/toggle/set_temperature/etc. entity_id: the target entity. data: optional JSON string with extra params.")
    def call_service(self, domain: str, service: str, entity_id: str, data: str = "{}") -> str:
        try:
            import json
            extra = json.loads(data) if data and data != "{}" else {}
            payload = {"entity_id": entity_id, **extra}

            resp = httpx.post(
                _api_url(f"services/{domain}/{service}"),
                headers=_headers(),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return f"OK: {domain}.{service} called on {entity_id}"
        except Exception as e:
            return f"Error calling {domain}.{service}: {e}"

    @tool("hass_list_entities", "List all Home Assistant entities for a given domain (light, switch, sensor, climate, media_player, cover, fan, automation)")
    def list_entities(self, domain: str) -> str:
        try:
            resp = httpx.get(
                _api_url("states"),
                headers=_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            entities = resp.json()

            filtered = [
                e for e in entities
                if e.get("entity_id", "").startswith(f"{domain}.")
            ]
            if not filtered:
                return f"No entities found for domain '{domain}'"

            lines = [f"{domain} entities ({len(filtered)}):"]
            for e in sorted(filtered, key=lambda x: x["entity_id"]):
                eid = e["entity_id"]
                state = e.get("state", "?")
                friendly = e.get("attributes", {}).get("friendly_name", eid)
                lines.append(f"  {friendly} ({eid}): {state}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing {domain} entities: {e}"

    @tool("hass_overview", "Get a quick overview of your smart home — lights, climate, and notable sensors")
    def overview(self) -> str:
        try:
            resp = httpx.get(
                _api_url("states"),
                headers=_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            entities = resp.json()

            sections = []

            # Lights
            lights = [e for e in entities if e["entity_id"].startswith("light.")]
            if lights:
                on = [e for e in lights if e["state"] == "on"]
                sections.append(f"💡 Lights: {len(on)}/{len(lights)} on")
                for l in on:
                    sections.append(f"  {l['attributes'].get('friendly_name', l['entity_id'])}")

            # Climate
            climate = [e for e in entities if e["entity_id"].startswith("climate.")]
            for c in climate:
                name = c["attributes"].get("friendly_name", c["entity_id"])
                current = c["attributes"].get("current_temperature", "?")
                target = c["attributes"].get("temperature", "?")
                sections.append(f"🌡 {name}: {current}° (target: {target}°)")

            # Key sensors
            for e in entities:
                eid = e["entity_id"]
                if "temperature" in eid and eid.startswith("sensor."):
                    name = e["attributes"].get("friendly_name", eid)
                    unit = e["attributes"].get("unit_of_measurement", "")
                    sections.append(f"📊 {name}: {e['state']} {unit}")

            return "\n".join(sections) if sections else "No smart home devices found"
        except Exception as e:
            return f"Error getting overview: {e}"


skill = HomeAssistantSkill()
