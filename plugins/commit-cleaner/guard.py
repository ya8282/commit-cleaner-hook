#!/usr/bin/env python3
"""Component B: PreToolUse guard. Deny and ask only, never updatedInput.

`deny > defer > ask > allow` is a documented multi-hook precedence rule
(hooks.md:1749). Multi-hook `updatedInput` behaviour is documented nowhere, and
rtk already returns it for the same key on the same commands. So enforcement
here is decisions, never rewrites.
"""
import json
import os
import re
import sys

from clean import clean
from gitconfig import load_patterns

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
# The anchor set includes a backtick: `` `git commit --no-verify ...` `` is a
# real command-substitution form, independent of quote-stripping.
_GIT_INVOCATION = re.compile(r"(?:^|[;&|(`]|\bdo\b|\bthen\b)\s*"
                             r"(?:\S*/)?(?:command\s+|env\s+)?"
                             r"(?:\w+=\S*\s+)*(?:\\)?git\b")

# A closed set of shell wrappers that hand a quoted argument to a nested
# shell: bash/sh/zsh/dash -c, and eval. Anchored the same way as
# _GIT_INVOCATION so an ordinary prose argument -- e.g. a commit message that
# happens to mention "sh -c" -- can't trigger it: the wrapper token has to
# sit right after a command separator (or the start of the string), and the
# quote has to follow it immediately, not several words later.
_SHELL_WRAP = re.compile(
    r"(?:^|[;&|(`]|\bdo\b|\bthen\b)\s*"
    r"(?:(?:bash|sh|zsh|dash)\s+-c\s+|eval\s+)"
)
_QUOTED_ARG = re.compile(r"""(['"])(.*?)\1""", re.S)


def _unwrap(cmd):
    """Peel one layer of `bash -c "..."` / `eval '...'` etc. so the guard
    inspects what the wrapper actually executes, not just which shell it
    hands the string to.

    Ceiling, documented rather than rediscovered: this covers only the
    closed wrapper set above with an immediately-following quoted argument.
    It does not cover arbitrary command substitution such as
    `$(echo git commit --no-verify ...)` -- recognising that in general
    means recognising arbitrary word-preceded indirection, which is
    unbounded. B1 defends against accidental attribution (a model reaching
    for --no-verify because it looks like ordinary git usage); a model
    doesn't accidentally reach for $(...) indirection to hide a flag, and if
    a commit lands anyway, component A still strips the trailer at
    commit-msg time regardless of how the `git commit` was invoked.
    """
    m = _SHELL_WRAP.search(cmd)
    if not m:
        return None
    qm = _QUOTED_ARG.match(cmd, m.end())
    if not qm:
        return None
    return qm.group(2)


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
    inner = _unwrap(cmd)
    if inner is not None:
        return _bash(inner)

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


_MCP_PR = re.compile(r"^mcp__.*__(create_pull_request|update_pull_request)$")
_MCP_COMMIT = re.compile(r"^mcp__.*__(create_or_update_file|delete_file|push_files)$")
_MCP_MERGE = re.compile(r"^mcp__.*__merge_pull_request$")
# Confirmed against github/github-mcp-server's README (Step 1): create_pull_request
# and update_pull_request use `body`; create_or_update_file, delete_file and
# push_files use `message`. `commit_message`/`description` kept as harmless
# no-ops for fields not present on any covered tool today.
_MCP_TEXT_FIELDS = ("body", "message", "commit_message", "description")

_DIRTY_REASON = (
    "This carries AI attribution (Co-Authored-By / session trailer). GitHub keeps "
    "an edit history that anyone with read access can view, so cleaning it after "
    "the fact would leave a permanent record of what was removed. Remove the "
    "attribution lines and retry."
)


def _is_dirty(text):
    # type: (str) -> bool
    """clean() assumes commit-message-shaped input, always trailing-newline
    terminated, and its result always is too (see clean.py). PR bodies and
    MCP text fields are not: they arrive without a trailing newline. Compare
    on a normalized copy so that convention doesn't register as a "cleaned"
    diff on every clean body."""
    if not text:
        return False
    normalized = text if text.endswith("\n") else text + "\n"
    return clean(normalized, load_patterns(os.getcwd())) != normalized


def _gh(cmd):
    if not re.search(r"(?:^|[;&|(]|\s)gh\s+(pr|issue)\b", cmd):
        return None
    if re.search(r"\bpr\s+merge\b", cmd) and re.search(r"--(body|subject)\b", cmd):
        return _out("deny",
                    "gh pr merge writes a commit message server-side, onto a branch "
                    "where no hook can clean it. Merge without --body/--subject.")

    m = re.search(r"--body[= ]\s*(['\"])(.*?)\1", cmd, re.S)
    if m and _is_dirty(m.group(2)):
        return _out("deny", _DIRTY_REASON)

    m = re.search(r"--body-file[= ]\s*(\S+)", cmd)
    if m:
        try:
            with open(m.group(1).strip("'\""), encoding="utf-8") as fh:
                if _is_dirty(fh.read()):
                    return _out("deny", f"{_DIRTY_REASON} (in {m.group(1)})")
        except Exception:
            return None
    return None


def _mcp(tool, tool_input):
    if _MCP_MERGE.match(tool):
        return _out("deny",
                    "merge_pull_request writes a commit message server-side, where "
                    "no hook can clean it.")
    if not (_MCP_PR.match(tool) or _MCP_COMMIT.match(tool)):
        return None
    for field in _MCP_TEXT_FIELDS:
        if _is_dirty(tool_input.get(field) or ""):
            return _out("deny", _DIRTY_REASON)
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
        if tool.startswith("mcp__"):
            return _mcp(tool, ti)
        if tool in ("Bash", "PowerShell"):
            cmd = ti.get("command")
            if not cmd:
                return None
            return _bash(cmd) or _gh(cmd)
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
