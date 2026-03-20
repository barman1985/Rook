"""
Built-in skill: File tools
============================
Read, write, list, and grep files on the server.
Run safe shell commands.
"""

import os
import logging
import subprocess
from pathlib import Path

from rook.skills.base import Skill, tool
from rook.core.config import cfg

logger = logging.getLogger(__name__)

BASE = cfg.base_dir
BLOCKED_COMMANDS = {"rm -rf /", "mkfs", "dd if=", ":(){ :|:", "shutdown", "reboot", "passwd"}


class FileToolsSkill(Skill):
    name = "file_tools"
    description = "Read, write, grep files and run safe commands"
    version = "1.0"

    @tool(
        "read_file",
        "Read a file from the server",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path (relative to base dir)"},
        }, "required": ["path"]}
    )
    def read_file(self, path: str) -> str:
        full = _safe_path(path)
        if not full:
            return f"Access denied: {path}"
        if not os.path.exists(full):
            return f"File not found: {path}"
        try:
            content = Path(full).read_text(errors="replace")
            if len(content) > 10000:
                return content[:5000] + f"\n\n... [{len(content)} chars total, truncated] ...\n\n" + content[-2000:]
            return content
        except Exception as e:
            return f"Error reading {path}: {e}"

    @tool(
        "write_file",
        "Write content to a file",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path (relative to base dir)"},
            "content": {"type": "string", "description": "Content to write"},
        }, "required": ["path", "content"]}
    )
    def write_file(self, path: str, content: str) -> str:
        full = _safe_path(path)
        if not full:
            return f"Access denied: {path}"
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            Path(full).write_text(content)
            return f"Written {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing {path}: {e}"

    @tool(
        "list_dir",
        "List files and directories",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directory path (default: base dir)"},
        }, "required": []}
    )
    def list_dir(self, path: str = "") -> str:
        full = _safe_path(path) if path else BASE
        if not full or not os.path.isdir(full):
            return f"Not a directory: {path}"
        try:
            entries = sorted(os.listdir(full))
            lines = [f"Contents of {path or '/'}:"]
            for e in entries:
                fp = os.path.join(full, e)
                if os.path.isdir(fp):
                    lines.append(f"  📁 {e}/")
                else:
                    size = os.path.getsize(fp)
                    lines.append(f"  📄 {e} ({_fmt_size(size)})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @tool(
        "grep_file",
        "Search for text in a file",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "pattern": {"type": "string", "description": "Text to search for"},
        }, "required": ["path", "pattern"]}
    )
    def grep_file(self, path: str, pattern: str) -> str:
        full = _safe_path(path)
        if not full or not os.path.exists(full):
            return f"File not found: {path}"
        try:
            lines = Path(full).read_text(errors="replace").splitlines()
            matches = []
            for i, line in enumerate(lines, 1):
                if pattern.lower() in line.lower():
                    matches.append(f"  {i}: {line.rstrip()}")
            if not matches:
                return f"No matches for '{pattern}' in {path}"
            result = f"Matches for '{pattern}' in {path}:\n" + "\n".join(matches[:30])
            if len(matches) > 30:
                result += f"\n  ... and {len(matches) - 30} more"
            return result
        except Exception as e:
            return f"Error: {e}"

    @tool(
        "run_command",
        "Run a safe shell command on the server",
        {"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
        }, "required": ["command"]}
    )
    def run_command(self, command: str) -> str:
        # Safety check
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return f"Blocked: '{command}' is not allowed."

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=30, cwd=BASE
            )
            output = (result.stdout + result.stderr).strip()
            if len(output) > 5000:
                output = output[:2500] + "\n...[truncated]...\n" + output[-1000:]
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out (30s limit)."
        except Exception as e:
            return f"Error: {e}"


def _safe_path(path: str) -> str:
    """Resolve path safely within base directory."""
    if not path:
        return BASE
    full = os.path.realpath(os.path.join(BASE, path))
    if not full.startswith(os.path.realpath(BASE)):
        return ""
    return full


def _fmt_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


skill = FileToolsSkill()
