"""
Built-in skill: Spotify
=========================
Play music, search, control playback, manage devices.

Setup: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET in .env
       Run OAuth flow once for user token.
"""

import os
import logging

import httpx

from rook.skills.base import Skill, tool
from rook.core.config import cfg

logger = logging.getLogger(__name__)

API = "https://api.spotify.com/v1"


class SpotifyClient:
    """Lightweight Spotify Web API client."""

    def __init__(self):
        self.token_path = os.path.join(cfg.base_dir, "spotify_token.json")
        self._token = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        import json
        if os.path.exists(self.token_path):
            with open(self.token_path) as f:
                data = json.load(f)
            self._token = data.get("access_token", "")
            # Refresh if expired
            if data.get("refresh_token"):
                self._try_refresh(data)
        return self._token or ""

    def _try_refresh(self, data: dict):
        try:
            resp = httpx.post("https://accounts.spotify.com/api/token", data={
                "grant_type": "refresh_token",
                "refresh_token": data["refresh_token"],
                "client_id": cfg.spotify_client_id,
                "client_secret": cfg.spotify_client_secret,
            })
            if resp.status_code == 200:
                new = resp.json()
                data["access_token"] = new["access_token"]
                self._token = new["access_token"]
                import json
                with open(self.token_path, "w") as f:
                    json.dump(data, f)
        except Exception as e:
            logger.error(f"Spotify token refresh failed: {e}")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def get(self, endpoint: str, params: dict = None) -> dict:
        r = httpx.get(f"{API}{endpoint}", headers=self._headers(), params=params, timeout=10)
        return r.json() if r.status_code == 200 else {}

    def put(self, endpoint: str, json_data: dict = None) -> bool:
        r = httpx.put(f"{API}{endpoint}", headers=self._headers(), json=json_data, timeout=10)
        return r.status_code in (200, 204)

    def post(self, endpoint: str, json_data: dict = None) -> dict:
        r = httpx.post(f"{API}{endpoint}", headers=self._headers(), json=json_data, timeout=10)
        return r.json() if r.status_code in (200, 201) else {}


class SpotifySkill(Skill):
    name = "spotify"
    description = "Spotify — play music, search, control playback, manage devices"
    version = "1.0"

    def __init__(self):
        super().__init__()
        self.enabled = cfg.spotify_enabled
        self._sp = SpotifyClient() if self.enabled else None

    @tool(
        "spotify_search_play",
        "Search for music on Spotify and play it",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for (song, artist, album, playlist)"},
            "device_name": {"type": "string", "description": "Target device name (optional)"},
        }, "required": ["query"]}
    )
    def search_and_play(self, query: str, device_name: str = "") -> str:
        data = self._sp.get("/search", {"q": query, "type": "track,playlist,album", "limit": 3})
        if not data:
            return "Search failed."

        device_id = self._find_device(device_name)

        # Try tracks first
        tracks = data.get("tracks", {}).get("items", [])
        if tracks:
            t = tracks[0]
            uri = t["uri"]
            self._sp.put("/me/player/play", {"uris": [uri], **({"device_id": device_id} if device_id else {})})
            return f"Playing: {t['name']} — {t['artists'][0]['name']}"

        # Try playlists
        playlists = data.get("playlists", {}).get("items", [])
        if playlists:
            p = playlists[0]
            self._sp.put("/me/player/play", {"context_uri": p["uri"], **({"device_id": device_id} if device_id else {})})
            return f"Playing playlist: {p['name']}"

        return f"Nothing found for: {query}"

    @tool(
        "spotify_play",
        "Resume playback or play a specific URI",
        {"type": "object", "properties": {
            "uri": {"type": "string", "description": "Spotify URI (optional — omit to resume)"},
            "device_name": {"type": "string", "description": "Target device (optional)"},
        }, "required": []}
    )
    def play(self, uri: str = "", device_name: str = "") -> str:
        device_id = self._find_device(device_name)
        params = {}
        if device_id:
            params["device_id"] = device_id

        body = {}
        if uri:
            if "playlist" in uri or "album" in uri or "artist" in uri:
                body["context_uri"] = uri
            else:
                body["uris"] = [uri]

        ok = self._sp.put(f"/me/player/play", body or None)
        return "Playback started." if ok else "Failed — no active device?"

    @tool(
        "spotify_control",
        "Control Spotify: pause, next, previous, volume",
        {"type": "object", "properties": {
            "action": {"type": "string", "description": "Action: pause, next, previous, volume"},
            "value": {"type": "integer", "description": "Volume level 0-100 (only for volume action)"},
        }, "required": ["action"]}
    )
    def control(self, action: str, value: int = 50) -> str:
        actions = {
            "pause": lambda: self._sp.put("/me/player/pause"),
            "next": lambda: httpx.post(f"{API}/me/player/next", headers=self._sp._headers(), timeout=10).status_code in (200, 204),
            "previous": lambda: httpx.post(f"{API}/me/player/previous", headers=self._sp._headers(), timeout=10).status_code in (200, 204),
            "volume": lambda: self._sp.put(f"/me/player/volume?volume_percent={max(0, min(100, value))}"),
        }
        fn = actions.get(action)
        if not fn:
            return f"Unknown action: {action}. Use: pause, next, previous, volume"
        ok = fn()
        return f"{action.capitalize()} done." if ok else f"{action} failed."

    @tool(
        "spotify_status",
        "Get current playback status",
        {"type": "object", "properties": {}, "required": []}
    )
    def status(self) -> str:
        data = self._sp.get("/me/player")
        if not data or not data.get("item"):
            return "Nothing playing."
        item = data["item"]
        artist = item.get("artists", [{}])[0].get("name", "?")
        name = item.get("name", "?")
        device = data.get("device", {}).get("name", "?")
        volume = data.get("device", {}).get("volume_percent", "?")
        playing = "Playing" if data.get("is_playing") else "Paused"
        return f"{playing}: {name} — {artist}\nDevice: {device} (vol {volume}%)"

    @tool(
        "spotify_devices",
        "List available Spotify devices",
        {"type": "object", "properties": {}, "required": []}
    )
    def devices(self) -> str:
        data = self._sp.get("/me/player/devices")
        devs = data.get("devices", [])
        if not devs:
            return "No devices available."
        lines = ["Spotify devices:"]
        for d in devs:
            active = " (active)" if d.get("is_active") else ""
            lines.append(f"  • {d['name']} ({d['type']}, vol {d.get('volume_percent', '?')}%){active}")
        return "\n".join(lines)

    @tool(
        "spotify_create_playlist",
        "Create a playlist with specific songs",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Playlist name"},
            "songs": {"type": "string", "description": "Comma-separated song queries (e.g. 'Bohemian Rhapsody, Stairway to Heaven')"},
        }, "required": ["name", "songs"]}
    )
    def create_playlist(self, name: str, songs: str) -> str:
        # Search for each track
        queries = [s.strip() for s in songs.split(",") if s.strip()]
        uris = []
        found = []
        for q in queries[:20]:
            data = self._sp.get("/search", {"q": q, "type": "track", "limit": 1})
            tracks = data.get("tracks", {}).get("items", [])
            if tracks:
                uris.append(tracks[0]["uri"])
                found.append(f"{tracks[0]['name']} — {tracks[0]['artists'][0]['name']}")

        if not uris:
            return "No tracks found."

        # Get user ID
        me = self._sp.get("/me")
        user_id = me.get("id")
        if not user_id:
            return "Cannot get user profile."

        # Create playlist
        playlist = self._sp.post(f"/users/{user_id}/playlists", {"name": name, "public": False})
        pid = playlist.get("id")
        if not pid:
            return "Failed to create playlist."

        # Add tracks
        self._sp.post(f"/playlists/{pid}/tracks", {"uris": uris})

        # Start playing
        self._sp.put("/me/player/play", {"context_uri": f"spotify:playlist:{pid}"})

        return f"Playlist '{name}' created with {len(uris)} tracks:\n" + "\n".join(f"  • {t}" for t in found)

    def _find_device(self, name: str = "") -> str:
        """Find device ID by name, or return first active."""
        if not name:
            return ""
        data = self._sp.get("/me/player/devices")
        for d in data.get("devices", []):
            if name.lower() in d.get("name", "").lower():
                return d["id"]
        return ""


skill = SpotifySkill()
