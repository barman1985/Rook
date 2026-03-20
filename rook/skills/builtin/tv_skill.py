"""
Built-in skill: TV / Chromecast
=================================
Control Chromecast with Google TV via ADB.

Setup: CHROMECAST_DEVICE_NAME in .env, ADB connected.
"""

import logging
import subprocess

from rook.skills.base import Skill, tool
from rook.core.config import cfg

logger = logging.getLogger(__name__)

APPS = {
    "youtube": "com.google.android.youtube.tv",
    "netflix": "com.netflix.ninja",
    "hbo": "com.hbo.hbonow",
    "disney": "com.disney.disneyplus",
    "spotify": "com.spotify.tv.android",
    "plex": "com.plexapp.android",
    "kodi": "org.xbmc.kodi",
    "prime": "com.amazon.amazonvideo.livingroom",
}


def _adb(cmd: str, timeout: int = 10) -> tuple[bool, str]:
    """Execute ADB command."""
    try:
        r = subprocess.run(
            f"adb {cmd}", shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        output = (r.stdout + r.stderr).strip()
        return r.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "ADB command timed out"
    except Exception as e:
        return False, str(e)


class TVSkill(Skill):
    name = "tv"
    description = "Control TV / Chromecast via ADB"
    version = "1.0"

    def __init__(self):
        super().__init__()
        self.enabled = cfg.tv_enabled

    @tool(
        "tv_power",
        "Turn TV on or off",
        {"type": "object", "properties": {
            "action": {"type": "string", "description": "'on' or 'off'"},
        }, "required": ["action"]}
    )
    def power(self, action: str) -> str:
        if action == "on":
            ok, msg = _adb("shell input keyevent KEYCODE_WAKEUP")
            return "TV waking up." if ok else f"Failed: {msg}"
        else:
            ok, msg = _adb("shell input keyevent KEYCODE_SLEEP")
            return "TV going to sleep." if ok else f"Failed: {msg}"

    @tool(
        "tv_launch_app",
        "Launch an app on TV (youtube, netflix, hbo, disney, spotify, plex, prime)",
        {"type": "object", "properties": {
            "app_name": {"type": "string", "description": "App name"},
        }, "required": ["app_name"]}
    )
    def launch_app(self, app_name: str) -> str:
        package = APPS.get(app_name.lower())
        if not package:
            return f"Unknown app: {app_name}. Available: {', '.join(APPS.keys())}"
        ok, msg = _adb(f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1")
        return f"Launching {app_name}." if ok else f"Failed: {msg}"

    @tool(
        "tv_control",
        "TV remote control: home, back, play/pause, volume_up, volume_down, mute",
        {"type": "object", "properties": {
            "action": {"type": "string", "description": "Action: home, back, play_pause, volume_up, volume_down, mute"},
        }, "required": ["action"]}
    )
    def control(self, action: str) -> str:
        keycodes = {
            "home": "KEYCODE_HOME",
            "back": "KEYCODE_BACK",
            "play_pause": "KEYCODE_MEDIA_PLAY_PAUSE",
            "volume_up": "KEYCODE_VOLUME_UP",
            "volume_down": "KEYCODE_VOLUME_DOWN",
            "mute": "KEYCODE_VOLUME_MUTE",
        }
        kc = keycodes.get(action)
        if not kc:
            return f"Unknown action: {action}. Use: {', '.join(keycodes.keys())}"
        ok, msg = _adb(f"shell input keyevent {kc}")
        return f"{action} done." if ok else f"Failed: {msg}"

    @tool(
        "tv_status",
        "Check if TV is on and what app is running",
        {"type": "object", "properties": {}, "required": []}
    )
    def status(self) -> str:
        ok, output = _adb("shell dumpsys power | grep 'Display Power'")
        if not ok:
            return "Cannot reach TV. Is ADB connected?"
        is_on = "ON" in output.upper()

        app = "unknown"
        ok2, output2 = _adb("shell dumpsys window | grep mCurrentFocus")
        if ok2 and output2:
            parts = output2.split("/")
            if parts:
                app = parts[0].split()[-1] if " " in parts[0] else parts[0]
                # Reverse lookup
                for name, pkg in APPS.items():
                    if pkg in app:
                        app = name
                        break

        return f"TV: {'ON' if is_on else 'OFF'}\nCurrent app: {app}"


skill = TVSkill()
