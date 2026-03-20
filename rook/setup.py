"""
rook.setup — Interactive first-time setup wizard
==================================================
Guides new users through configuration.

Usage:
    python -m rook.setup
"""

import os
import sys
import shutil
from pathlib import Path


# Colors for terminal
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


def banner():
    print(f"""
{BOLD}♜ Rook — Setup Wizard{RESET}
{DIM}Your strategic AI advantage{RESET}
{'─' * 40}
""")


def ask(prompt: str, required: bool = True, default: str = "", secret: bool = False) -> str:
    """Ask user for input."""
    suffix = f" [{default}]" if default else ""
    suffix += " (required)" if required and not default else ""

    while True:
        if secret:
            import getpass
            value = getpass.getpass(f"  {prompt}{suffix}: ")
        else:
            value = input(f"  {prompt}{suffix}: ").strip()

        if not value and default:
            return default
        if not value and required:
            print(f"  {RED}This field is required.{RESET}")
            continue
        return value


def ask_yn(prompt: str, default: bool = True) -> bool:
    """Yes/no question."""
    yn = "[Y/n]" if default else "[y/N]"
    value = input(f"  {prompt} {yn}: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def section(title: str):
    print(f"\n{CYAN}{BOLD}{title}{RESET}")
    print(f"{DIM}{'─' * 40}{RESET}")


def success(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def main():
    banner()

    env_path = Path(".env")
    if env_path.exists():
        if not ask_yn(f"{YELLOW}.env already exists. Overwrite?{RESET}", default=False):
            print("Setup cancelled. Edit .env manually if needed.")
            sys.exit(0)

    config = {}

    # ── Step 1: Required keys ──
    section("Step 1: Required — API keys")
    print(f"  {DIM}You need an Anthropic API key and a Telegram bot.{RESET}")
    print(f"  {DIM}Anthropic: https://console.anthropic.com/{RESET}")
    print(f"  {DIM}Telegram: message @BotFather on Telegram{RESET}")
    print()

    config["ANTHROPIC_API_KEY"] = ask("Anthropic API key", secret=True)
    config["TELEGRAM_BOT_TOKEN"] = ask("Telegram bot token")
    config["TELEGRAM_CHAT_ID"] = ask("Your Telegram chat ID (message @userinfobot to get it)")

    success("Core config ready")

    # ── Step 2: Google ──
    section("Step 2: Optional — Google Calendar + Gmail")
    if ask_yn("Enable Google Calendar and Gmail?"):
        print(f"""
  {DIM}To set up Google APIs:
  1. Go to https://console.cloud.google.com/
  2. Create a project (or select existing)
  3. Enable: Google Calendar API + Gmail API
  4. Create OAuth 2.0 credentials (Desktop application)
  5. Download the JSON → save as 'credentials.json' in this directory
  6. On first run, Rook will open a browser for OAuth consent{RESET}
""")
        creds_path = ask("Path to credentials.json", required=False, default="credentials.json")
        if creds_path:
            config["GOOGLE_CREDENTIALS_PATH"] = creds_path
            if not Path(creds_path).exists():
                warn(f"{creds_path} not found yet — add it before running Rook")
            else:
                success("credentials.json found")

                # Generate token.json via OAuth flow
                if ask_yn("Run OAuth flow now to generate token.json?"):
                    _run_oauth_flow(creds_path)
    else:
        warn("Google Calendar and Gmail disabled")

    # ── Step 3: Spotify ──
    section("Step 3: Optional — Spotify")
    if ask_yn("Enable Spotify control?", default=False):
        print(f"  {DIM}Create app at https://developer.spotify.com/dashboard{RESET}")
        config["SPOTIFY_CLIENT_ID"] = ask("Spotify Client ID")
        config["SPOTIFY_CLIENT_SECRET"] = ask("Spotify Client Secret", secret=True)
        config["SPOTIFY_REDIRECT_URI"] = ask("Redirect URI", default="http://localhost:8888/callback")
        success("Spotify configured")
    else:
        warn("Spotify disabled")

    # ── Step 4: TV ──
    section("Step 4: Optional — TV / Chromecast")
    if ask_yn("Enable TV control (Chromecast with Google TV)?", default=False):
        config["CHROMECAST_DEVICE_NAME"] = ask("Chromecast device name (from ADB)")
        success("TV configured")
    else:
        warn("TV control disabled")

    # ── Step 5: X/Twitter ──
    section("Step 5: Optional — X (Twitter) posting")
    if ask_yn("Enable X/Twitter posting?", default=False):
        print(f"  {DIM}Create app at https://developer.x.com/en/portal{RESET}")
        config["X_API_KEY"] = ask("X API Key")
        config["X_API_SECRET"] = ask("X API Secret", secret=True)
        config["X_ACCESS_TOKEN"] = ask("X Access Token")
        config["X_ACCESS_TOKEN_SECRET"] = ask("X Access Token Secret", secret=True)
        success("X posting configured")
    else:
        warn("X posting disabled")

    # ── Step 6: Advanced ──
    section("Step 6: Advanced settings")
    config["TIMEZONE"] = ask("Timezone", default="Europe/Prague")
    config["LOG_LEVEL"] = ask("Log level", default="INFO")

    # ── Write .env ──
    section("Writing configuration")

    lines = ["# Rook configuration — generated by setup wizard", ""]
    for key, value in config.items():
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n")
    success(f".env written ({len(config)} settings)")

    # ── Install dependencies ──
    section("Dependencies")
    if ask_yn("Install Python dependencies now?"):
        import subprocess
        print(f"  {DIM}Running pip install -r requirements.txt ...{RESET}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            success("Dependencies installed")
        else:
            warn(f"Some dependencies failed: {result.stderr[:200]}")
            print(f"  {DIM}Run manually: pip install -r requirements.txt{RESET}")
    else:
        warn("Run manually: pip install -r requirements.txt")

    # ── Done ──
    print(f"""
{'─' * 40}
{GREEN}{BOLD}✓ Rook is configured!{RESET}

{BOLD}To start:{RESET}
  python -m rook.main

{BOLD}Features enabled:{RESET}""")

    if "GOOGLE_CREDENTIALS_PATH" in config:
        print(f"  {GREEN}✓{RESET} Google Calendar + Gmail")
    if "SPOTIFY_CLIENT_ID" in config:
        print(f"  {GREEN}✓{RESET} Spotify")
    if "CHROMECAST_DEVICE_NAME" in config:
        print(f"  {GREEN}✓{RESET} TV / Chromecast")
    if "X_API_KEY" in config:
        print(f"  {GREEN}✓{RESET} X (Twitter) posting")

    print(f"""
{DIM}Telegram commands:
  /start  — welcome message
  /status — system status
  /skills — list loaded skills{RESET}

{BOLD}♜ Rook — your strategic advantage{RESET}
""")


def _run_oauth_flow(creds_path: str):
    """Run Google OAuth flow to generate token.json."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        SCOPES = [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
        ]

        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)

        with open("token.json", "w") as f:
            f.write(creds.to_json())

        success("token.json created — Google services ready!")

    except ImportError:
        warn("google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib")
        warn("Then run: python -m rook.setup again")
    except Exception as e:
        warn(f"OAuth flow failed: {e}")
        warn("You can run this later: python -m rook.setup")


if __name__ == "__main__":
    main()
