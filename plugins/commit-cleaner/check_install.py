#!/usr/bin/env python3
"""Component C: SessionStart. Is the commit-msg cleaner actually alive here?

Scope: the repo this session started in. It does not cover a mid-session cd,
multi-root workspaces, worktrees added later, or repos that were not open when
the invariant broke. A cheap check that catches the common case.
"""
import json
import os
import subprocess
import sys

from install import resolve_hooks_dir

MSG = ("commit-cleaner is not installed in this repo, so AI attribution "
       "trailers will not be stripped from commits. Install it by running "
       "`python3 ${CLAUDE_PLUGIN_ROOT}/install.py`.")


def status(repo):
    """Returns a warning string, or None when the invariant holds."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo, capture_output=True, text=True, timeout=5,
        )
        if inside.returncode != 0:
            return None
        hook = resolve_hooks_dir(repo) / "commit-msg"
        if not hook.exists() or "commit-cleaner" not in hook.read_text():
            return MSG
        if not os.access(str(hook), os.X_OK):
            return (
                f"commit-cleaner's commit-msg hook exists but is not "
                f"executable, so git ignores it. Run `chmod +x {hook}`."
            )
    except Exception:
        return None
    return None


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    warning = status(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if warning:
        print(json.dumps({"systemMessage": warning}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
