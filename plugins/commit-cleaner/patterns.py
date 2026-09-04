"""The attribution pattern set. Single source of truth for every component.

Each pattern is matched against a whole line with re.search, case-insensitively.
Co-Authored-By keys on the ANTHROPIC EMAIL, not the display name: a human
co-author named Claude must survive.
"""
import re
import sys
from typing import Optional  # noqa: F401

DEFAULT_PATTERNS = [
    r"^\s*Co-Authored-By:.*@anthropic\.com\s*>?\s*$",
    r"^\s*Claude-Session:\s*\S+\s*$",
    r"^\s*\S*-?Session:\s*https?://claude\.ai/code/session_\S+\s*$",
    r"^\s*\U0001f916?\s*Generated with \[Claude Code\]\(https?://[^)]*\)\s*$",
    r"^\s*\U0001f916?\s*Generated with Claude Code\s*$",
]

# Opt-in. Uncomment in a commitcleaner.patterns file rather than editing this.
#   ^\s*Co-Authored-By:.*@cursor\.com\s*>?\s*$
#   ^\s*Co-Authored-By:.*\bcodex\b.*$
#   ^\s*Co-Authored-By:.*\bcopilot\b.*$
#   ^\s*Co-Authored-By:.*\baider\b.*$
#   ^\s*Co-Authored-By:.*\bdevin\b.*$


def compile_patterns(extra=None, use_defaults=True):
    # type: (Optional[list[str]], bool) -> list[re.Pattern[str]]
    """Compile the active pattern set. A pattern that will not compile is
    skipped with a note on stderr: a bad user regex must never fail a commit."""
    sources = list(DEFAULT_PATTERNS) if use_defaults else []
    sources.extend(extra or [])
    out = []
    for src in sources:
        try:
            out.append(re.compile(src, re.IGNORECASE))
        except re.error as exc:
            print(f"commit-cleaner: skipping bad pattern {src!r} ({exc})", file=sys.stderr)
    return out
