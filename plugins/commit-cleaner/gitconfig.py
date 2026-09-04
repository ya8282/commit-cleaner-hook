"""Configuration comes from `git config`, never from the environment.

A git hook does not inherit the Claude Code session environment, so an env var
would make the same repo strip differently depending on who typed the command.
"""
import os
import subprocess
from re import Pattern  # noqa: F401
from typing import Optional  # noqa: F401

from patterns import compile_patterns


def _git_config(key, cwd):
    # type: (str, Optional[str]) -> Optional[str]
    try:
        out = subprocess.run(
            ["git", "config", "--get", key],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and value else None


def _read_pattern_file(path):
    # type: (str) -> list[str]
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return []
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def load_patterns(cwd=None):
    # type: (Optional[str]) -> list[Pattern[str]]
    """Never raises. Any failure degrades to the built-in defaults."""
    try:
        extra_path = _git_config("commitcleaner.patterns", cwd)
        extra = _read_pattern_file(extra_path) if extra_path else []
        use_defaults = _git_config("commitcleaner.defaults", cwd) != "false"
        if not extra and not use_defaults:
            use_defaults = True  # never end up with an empty pattern set
        return compile_patterns(extra=extra, use_defaults=use_defaults)
    except Exception:
        return compile_patterns()
