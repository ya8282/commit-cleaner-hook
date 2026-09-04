#!/usr/bin/env python3
"""Component B: PreToolUse guard. Deny and ask only, never updatedInput.

`deny > defer > ask > allow` is a documented multi-hook precedence rule
(hooks.md:1749). Multi-hook `updatedInput` behaviour is documented nowhere, and
rtk already returns it for the same key on the same commands. So enforcement
here is decisions, never rewrites.
"""
import json
import re
import sys

HOOK_NAME = "commit-msg"

# Env assignments that redirect git's config lookup or disable hook frameworks.
_ENV_PREFIX = re.compile(
    r"\b(GIT_CONFIG_GLOBAL|GIT_CONFIG_SYSTEM|GIT_DIR|GIT_WORK_TREE|HOME|XDG_CONFIG_HOME"
    r"|HUSKY|SKIP_HOOKS|LEFTHOOK)\s*=",
    re.IGNORECASE,
)
# git accepts unambiguous long-option prefixes: --no-verif and --no-veri both work.
_NO_VERIFY = re.compile(r"--no-veri(f(y)?)?(?![\w-])")
# -n inside a short-flag cluster (-n, -nm, -anm). Not --no-*.
_SHORT_N = re.compile(r"(?<![\w-])-[a-zA-Z]*n[a-zA-Z]*(?![\w-])")
_INLINE_HOOKSPATH = re.compile(r"-c\s+core\.hooksPath\s*=", re.IGNORECASE)
_CONFIG_HOOKSPATH = re.compile(r"\bconfig\b.*\bcore\.hooksPath\b", re.IGNORECASE)
_HOOK_TARGET = re.compile(r"(hooks/|\.husky/|/)" + HOOK_NAME + r"\b")
# Bare `VAR=val git ...` (no `env` keyword) is standard shell inline-assignment
# syntax and just as real an evasion as `env FOO=1 git`, so the assignment
# group is unconditional, not gated behind literal "env ".
_GIT_INVOCATION = re.compile(r"(?:^|[;&|(]|\bdo\b|\bthen\b)\s*"
                             r"(?:\S*/)?(?:command\s+|env\s+)?"
                             r"(?:\w+=\S*\s+)*(?:\\)?git\b")


def strip_code(cmd):
    # type: (str) -> str
    """Guard mode: remove heredoc bodies and quoted spans so prose ABOUT a
    command is not mistaken for running it. Cleaners do the opposite."""
    c = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\1$", " ", cmd, flags=re.S | re.M)
    c = re.sub(r"'[^']*'|\"[^\"]*\"", " ", c)
    return c.replace("rtk ", "")


def _out(decision, reason):
    # type: (str, str) -> dict
    """Flat shape: callers (tests, Task 8) read d["permissionDecision"]
    directly. main() wraps this in the hookSpecificOutput envelope that the
    actual PreToolUse protocol requires when writing to stdout."""
    return {
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }


def _bash(cmd):
    c = strip_code(cmd)
    is_commit = bool(_GIT_INVOCATION.search(c)) and re.search(r"\bcommit\b", c)

    if is_commit:
        if _NO_VERIFY.search(c) or _SHORT_N.search(c):
            return _out("deny",
                        "--no-verify skips the commit-msg hook that strips AI "
                        "attribution. Run the commit without it. To skip a slow "
                        "pre-commit hook instead, disable that specific hook "
                        "(pre-commit: SKIP=<id>), not every hook.")
        if _INLINE_HOOKSPATH.search(c) or _ENV_PREFIX.search(c):
            return _out("deny",
                        "This redirects git's hook or config lookup, which "
                        "disables the commit-msg cleaner. Run the commit without it.")

    if _CONFIG_HOOKSPATH.search(c) and re.search(r"(?:^|[;&|(]|\s)git\b", c):
        return _out("ask",
                    "This changes where git looks for hooks, so the commit-cleaner "
                    "hook may stop running. Fine for `husky init` or `lefthook "
                    "install` - re-run `commit-cleaner install` afterwards.")

    if re.search(r"(?:^|[;&|(])\s*(chmod|rm)\b", c) and _HOOK_TARGET.search(c):
        return _out("deny",
                    "This removes or disables the commit-msg hook that strips AI "
                    "attribution. Use `commit-cleaner install --uninstall` if you "
                    "mean to remove it.")
    return None


_GIT_PATH = re.compile(r"[/\\]\.git[/\\](hooks[/\\]|config$)")


def _file_tool(tool_input):
    path = tool_input.get("file_path") or ""
    if _GIT_PATH.search(path):
        return _out("ask",
                    "This writes inside .git/, where the commit-cleaner hook lives. "
                    "Editing it by hand can silently disable attribution stripping.")
    return None


def decide(payload):
    """Returns a flat {permissionDecision, permissionDecisionReason} dict,
    or None to say nothing. main() wraps it in the hookSpecificOutput
    envelope before writing to stdout."""
    try:
        tool = payload.get("tool_name") or ""
        ti = payload.get("tool_input") or {}
        if tool in ("Bash", "PowerShell"):
            cmd = ti.get("command")
            return _bash(cmd) if cmd else None
        if tool in ("Write", "Edit", "NotebookEdit"):
            return _file_tool(ti)
    except Exception:
        return None
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    result = decide(payload)
    if result:
        envelope = {"hookSpecificOutput": {"hookEventName": "PreToolUse", **result}}
        print(json.dumps(envelope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
