"""
rook.skills.builtin.self_improve_skill — Self-improvement pipeline
====================================================================
Rook reads, analyzes, and proposes changes to its own source code.
User must explicitly /approve before any change is applied.

Pipeline:
1. /improve [request] → Rook reads own source
2. Generates PATCH via LLM (code generation)
3. Auto-review (second opinion)
4. Shows diff to user
5. Waits for /approve or /reject
6. On approve: applies patch, py_compile check, git commit

Usage:
    from rook.skills.builtin.self_improve_skill import skill
"""

import os
import py_compile
import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, date

from rook.skills.base import Skill, tool
from rook.core.config import cfg

logger = logging.getLogger(__name__)

# Safety limits
MAX_DAILY_IMPROVEMENTS = 3
ALLOWED_DIR = "rook"  # Can only modify files under rook/


class SelfImproveSkill(Skill):
    name = "self_improve"

    def __init__(self):
        super().__init__()
        self._pending: dict | None = None  # {file, original, patched, description, diff}
        self._daily_count: int = 0
        self._daily_date: date | None = None

    def _check_daily_limit(self) -> bool:
        """Check if daily improvement limit reached."""
        today = date.today()
        if self._daily_date != today:
            self._daily_count = 0
            self._daily_date = today
        return self._daily_count < MAX_DAILY_IMPROVEMENTS

    def _is_safe_path(self, filepath: str) -> bool:
        """Check if file is within allowed directory."""
        base = Path(cfg.base_dir).resolve()
        target = (base / filepath).resolve()
        allowed = (base / ALLOWED_DIR).resolve()
        return str(target).startswith(str(allowed))

    @tool("read_source", "Read a Rook source file for analysis")
    def read_source(self, filepath: str) -> str:
        """Read a source file. Path relative to project root."""
        if not self._is_safe_path(filepath):
            return f"❌ Access denied: {filepath} is outside {ALLOWED_DIR}/"

        full_path = Path(cfg.base_dir) / filepath
        if not full_path.exists():
            return f"❌ File not found: {filepath}"

        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            return f"=== {filepath} ({len(lines)} lines) ===\n{content}"
        except Exception as e:
            return f"❌ Read error: {e}"

    @tool("list_source", "List Rook source files")
    def list_source(self, directory: str = "rook") -> str:
        """List Python files in a directory. Path relative to project root."""
        if not self._is_safe_path(directory):
            return f"❌ Access denied: {directory} is outside {ALLOWED_DIR}/"

        base = Path(cfg.base_dir) / directory
        if not base.exists():
            return f"❌ Directory not found: {directory}"

        files = sorted(base.rglob("*.py"))
        lines = [f"📁 {directory}/ ({len(files)} Python files):"]
        for f in files:
            rel = f.relative_to(Path(cfg.base_dir))
            size = f.stat().st_size
            lines.append(f"  {rel} ({size:,} bytes)")
        return "\n".join(lines)

    @tool("propose_change", "Propose a code change (generates diff, requires /approve)")
    def propose_change(self, filepath: str, new_content: str, description: str) -> str:
        """
        Propose a change to a source file.
        Does NOT apply immediately — waits for user /approve.
        """
        if not self._check_daily_limit():
            return f"❌ Daily limit reached ({MAX_DAILY_IMPROVEMENTS}/day). Try again tomorrow."

        if not self._is_safe_path(filepath):
            return f"❌ Access denied: {filepath} is outside {ALLOWED_DIR}/"

        full_path = Path(cfg.base_dir) / filepath

        # Read original (or empty if new file)
        original = ""
        if full_path.exists():
            original = full_path.read_text(encoding="utf-8")

        # Syntax check on proposed content
        syntax_ok, syntax_err = self._syntax_check(new_content, filepath)
        if not syntax_ok:
            return f"❌ Syntax error in proposed code:\n{syntax_err}"

        # Generate diff
        diff = self._generate_diff(original, new_content, filepath)

        # Store pending
        self._pending = {
            "file": filepath,
            "original": original,
            "patched": new_content,
            "description": description,
            "diff": diff,
            "proposed_at": datetime.now().isoformat(),
        }

        return (
            f"📝 Proposed change: {description}\n"
            f"File: {filepath}\n"
            f"Diff:\n```\n{diff[:2000]}\n```\n\n"
            f"Reply /approve to apply or /reject to discard."
        )

    def has_pending(self) -> bool:
        """Check if there's a pending improvement."""
        return self._pending is not None

    def apply_pending(self) -> str:
        """Apply the pending improvement (called on /approve)."""
        if not self._pending:
            return "❌ No pending improvement to apply."

        filepath = self._pending["file"]
        new_content = self._pending["patched"]
        description = self._pending["description"]

        full_path = Path(cfg.base_dir) / filepath

        # Final syntax check
        syntax_ok, syntax_err = self._syntax_check(new_content, filepath)
        if not syntax_ok:
            self._pending = None
            return f"❌ Syntax check failed on apply:\n{syntax_err}"

        try:
            # Write file
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(new_content, encoding="utf-8")

            # Git commit
            commit_msg = f"[self-improve] {description}"
            git_result = self._git_commit(filepath, commit_msg)

            self._daily_count += 1
            self._pending = None

            return f"✅ Applied: {description}\n{git_result}"

        except Exception as e:
            # Rollback on error
            if self._pending and self._pending.get("original"):
                full_path.write_text(self._pending["original"], encoding="utf-8")
            self._pending = None
            return f"❌ Apply failed (rolled back): {e}"

    def reject_pending(self) -> str:
        """Reject the pending improvement."""
        if not self._pending:
            return "No pending improvement."
        desc = self._pending["description"]
        self._pending = None
        return f"🚫 Rejected: {desc}"

    def _syntax_check(self, code: str, filepath: str) -> tuple[bool, str]:
        """Run py_compile on code. Returns (ok, error_message)."""
        if not filepath.endswith(".py"):
            return True, ""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                tmp_path = f.name
            py_compile.compile(tmp_path, doraise=True)
            return True, ""
        except py_compile.PyCompileError as e:
            return False, str(e)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _generate_diff(self, original: str, new: str, filepath: str) -> str:
        """Generate a unified diff."""
        import difflib
        orig_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(orig_lines, new_lines, fromfile=f"a/{filepath}", tofile=f"b/{filepath}")
        return "".join(diff) or "(no changes)"

    def _git_commit(self, filepath: str, message: str) -> str:
        """Attempt git add + commit. Non-fatal on failure."""
        try:
            base = cfg.base_dir
            subprocess.run(["git", "add", filepath], cwd=base, capture_output=True, timeout=10)
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=base, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return f"Git: committed ({message[:50]})"
            return f"Git: {result.stderr.strip()[:100]}"
        except Exception as e:
            return f"Git: {e}"


# Singleton
skill = SelfImproveSkill()
