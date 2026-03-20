"""
rook.core.config — Single source of configuration
===================================================
All config flows through here. No module reads .env directly.

Usage:
    from rook.core.config import cfg

    if cfg.spotify_enabled:
        ...
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Rook configuration — loaded once at startup."""

    # ── Required ──
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Models ──
    main_model: str = "claude-sonnet-4-20250514"
    router_model: str = "claude-haiku-4-5-20251001"
    escalation_model: str = "claude-opus-4-20250514"

    # ── Google ──
    google_credentials_path: str = ""

    # ── Spotify ──
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8888/callback"

    # ── TV ──
    chromecast_device_name: str = ""

    # ── Voice ──
    piper_model_path: str = "tts_models/cs_CZ-jirka-medium.onnx"

    # ── System ──
    base_dir: str = ""
    db_path: str = "rook.db"
    log_level: str = "INFO"
    timezone: str = "Europe/Prague"

    # ── Computed (set in __post_init__) ──
    google_enabled: bool = field(init=False, default=False)
    spotify_enabled: bool = field(init=False, default=False)
    tv_enabled: bool = field(init=False, default=False)
    voice_enabled: bool = field(init=False, default=False)

    def __post_init__(self):
        if not self.base_dir:
            self.base_dir = str(Path(__file__).parent.parent.parent)
        self.google_enabled = bool(self.google_credentials_path)
        self.spotify_enabled = bool(self.spotify_client_id and self.spotify_client_secret)
        self.tv_enabled = bool(self.chromecast_device_name)
        self.voice_enabled = Path(self.piper_model_path).exists() if self.piper_model_path else False

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Config":
        """Load config from .env file + environment variables."""
        # Load .env if exists
        env_file = Path(env_path)
        env_vars = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()

        def get(key: str, default: str = "") -> str:
            return os.environ.get(key, env_vars.get(key, default))

        return cls(
            anthropic_api_key=get("ANTHROPIC_API_KEY"),
            telegram_bot_token=get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=get("TELEGRAM_CHAT_ID"),
            main_model=get("MAIN_MODEL", "claude-sonnet-4-20250514"),
            router_model=get("ROUTER_MODEL", "claude-haiku-4-5-20251001"),
            escalation_model=get("ESCALATION_MODEL", "claude-opus-4-20250514"),
            google_credentials_path=get("GOOGLE_CREDENTIALS_PATH"),
            spotify_client_id=get("SPOTIFY_CLIENT_ID"),
            spotify_client_secret=get("SPOTIFY_CLIENT_SECRET"),
            spotify_redirect_uri=get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"),
            chromecast_device_name=get("CHROMECAST_DEVICE_NAME"),
            piper_model_path=get("PIPER_MODEL_PATH", "tts_models/cs_CZ-jirka-medium.onnx"),
            db_path=get("DB_PATH", "rook.db"),
            log_level=get("LOG_LEVEL", "INFO"),
            timezone=get("TIMEZONE", "Europe/Prague"),
        )

    def validate(self) -> list[str]:
        """Return list of missing required config items."""
        errors = []
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID")
        return errors

    def summary(self) -> str:
        """Human-readable config summary for startup log."""
        features = []
        if self.google_enabled:
            features.append("Google (Calendar + Gmail)")
        if self.spotify_enabled:
            features.append("Spotify")
        if self.tv_enabled:
            features.append("TV/Chromecast")
        if self.voice_enabled:
            features.append("Voice (Piper TTS)")
        return (
            f"Model: {self.main_model}\n"
            f"Features: {', '.join(features) or 'none'}\n"
            f"DB: {self.db_path}\n"
            f"TZ: {self.timezone}"
        )


# Singleton — initialized on first import
cfg = Config.from_env()
