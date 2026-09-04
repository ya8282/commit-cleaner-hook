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
import signal
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
# Where one invocation stops and the next command starts. The `--` of
# `npm run build -- -n` is not a separator: that argument list belongs to
# whatever command owns it, and if that command is not git, no git
# invocation match started there in the first place.
_SEGMENT_END = re.compile(r"[;&|)`]|\bdo\b|\bthen\b")

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


def _commit_segments(c):
    # type: (str) -> list
    """The `git commit` invocations in a compound command, each cut down to
    its own words.

    Searching the whole command string for `-n` denied `git add -n . && git
    commit -m wip`, `git log -n 5; git commit -m y`, and `git commit -m x &&
    npm run build -- -n` -- three ordinary shapes where the flag belongs to a
    different command entirely. Worse, the deny text named --no-verify, so the
    obvious retry was the same command again.

    Each invocation runs from the start of its _GIT_INVOCATION match (which
    includes any leading `VAR=val` assignments and `command`/`env`/path
    prefix, so those stay attached to the right git) to the next shell
    separator. strip_code has already removed quoted spans, so a separator
    found here is real syntax, not text inside an argument.
    """
    out = []
    for m in _GIT_INVOCATION.finditer(c):
        end = _SEGMENT_END.search(c, m.end())
        seg = c[m.start():end.start() if end else len(c)]
        if re.search(r"\bcommit\b", seg):
            out.append(seg)
    return out


def _bash(cmd):
    inner = _unwrap(cmd)
    if inner is not None:
        return _bash(inner)

    c = strip_code(cmd)

    for seg in _commit_segments(c):
        flag = _NO_VERIFY.search(seg) or _SHORT_N.search(seg)
        if flag:
            return _out("deny",
                        f"`{flag.group(0)}` on this `git commit` means --no-verify, "
                        "which skips the commit-msg hook that strips AI attribution. "
                        "Run the commit without that flag. To skip a slow pre-commit "
                        "hook instead, disable that specific hook (pre-commit: "
                        "SKIP=<id>), not every hook.")
        if _INLINE_HOOKSPATH.search(seg) or _ENV_PREFIX.search(seg):
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
# add_issue_comment and add_comment_to_pending_review confirmed against the
# current github-mcp-server README. create_pending_pull_request_review /
# submit_pending_pull_request_review, as named in the fix request, no longer
# exist there: the server has since consolidated create/submit/delete review
# actions into one tool, pull_request_review_write (`body` is optional,
# `method` selects the action) -- covered here in its place.
# add_reply_to_pull_request_comment is the reply half of the review-comment
# pair: same `body`, same permanent public edit history, and a model answering
# a review comment is exactly where a trailer gets pasted.
_MCP_COMMENT = re.compile(
    r"^mcp__.*__(add_issue_comment|add_comment_to_pending_review"
    r"|add_reply_to_pull_request_comment|pull_request_review_write)$"
)
# Issues and discussions were listed as out of scope, but `_gh` matches
# `gh\s+(pr|issue)\b`, so `gh issue create --body` has been denied from the
# start. Leaving the MCP path open meant the same content was blocked or
# allowed purely by which tool the model happened to reach for. The CLI's
# behaviour is the one to match: a body is a body.
_MCP_ISSUE = re.compile(r"^mcp__.*__(issue_write|discussion_comment_write)$")
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


_SENTINEL = "\x00-commit-cleaner-guard-sentinel-\x00"


def _is_dirty(text):
    # type: (str) -> bool
    """clean() assumes commit-message-shaped input, always trailing-newline
    terminated, and its result always is too (see clean.py). PR bodies and
    MCP text fields are not: they arrive without a trailing newline, so
    normalize before comparing or every clean body reads as "cleaned."

    Separately, clean() refuses to strip a message down to nothing (a real
    commit can't have an empty message), so a body that is ENTIRELY
    attribution -- no other content -- round-trips unchanged and would
    otherwise read as "not dirty," the opposite of correct here: PR bodies
    have no such floor. A trailing sentinel line, built to match none of the
    default or custom patterns, keeps clean()'s kept-lines list non-empty so
    it actually strips the attribution instead of preserving it.
    """
    if not text:
        return False
    normalized = text if text.endswith("\n") else text + "\n"
    guarded = normalized + _SENTINEL + "\n"
    return clean(guarded, load_patterns(os.getcwd())) != guarded


# gh accepts a short form for every flag this guard cares about, and a model
# reaching for `gh pr create -b "..."` is not doing anything exotic -- it is the
# form the tool's own --help lists first. Matching only the long spelling left
# the whole of B2 bypassable by typing two fewer characters.
#   -b == --body        (pr create / pr edit / pr merge / issue create / ...)
#   -F == --body-file   (pr create / pr edit / pr merge)
#   -t == --title       on pr create/edit, --subject on pr merge
# `--body-file` also starts with `--body`, which is why the separator class
# ([= ]) is required: it keeps `--body-file x` out of the body-value match.
# Ceiling: a value glued to its short flag (`-bhello`) is not matched. gh
# accepts it, but it cannot carry a multi-line trailer without quoting, and
# widening the separator would make `-b` match inside ordinary words.
_BODY_FLAG = r"(?:--body|(?<![\w-])-b)"
_BODY_FILE_FLAG = r"(?:--body-file|(?<![\w-])-F)"
_MERGE_MSG_FLAG = re.compile(
    r"--(?:body|subject|body-file)\b|(?<![\w-])-[btF](?![\w-])"
)
_BODY_VALUE = re.compile(_BODY_FLAG + r"[= ]\s*(?:(['\"])(.*?)\1|(\S+))", re.S)
_BODY_FILE_VALUE = re.compile(_BODY_FILE_FLAG + r"[= ]\s*(\S+)")


def _gh(cmd):
    # Subcommand detection (is this `pr merge`?) runs on strip_code output so
    # a body that merely mentions "gh pr merge" in prose can't self-trigger
    # the merge guard -- convention 4, a guard pass and a cleaner pass over
    # separately-derived strings. Body *extraction* stays on the raw command:
    # the body lives inside exactly the quotes strip_code removes.
    stripped = strip_code(cmd)
    if not re.search(r"(?:^|[;&|(]|\s)gh\s+(pr|issue)\b", stripped):
        return None
    if re.search(r"\bpr\s+merge\b", stripped) and _MERGE_MSG_FLAG.search(stripped):
        return _out("deny",
                    "gh pr merge writes a commit message server-side, onto a branch "
                    "where no hook can clean it. Merge without "
                    "--body/--subject/--body-file (-b/-t/-F).")

    # Every occurrence, not just the first: `gh pr create -t "..." -b "..."`
    # would otherwise hinge on which flag came first.
    for m in _BODY_VALUE.finditer(cmd):
        text = m.group(2) if m.group(1) else m.group(3)
        if _is_dirty(text):
            return _out("deny", _DIRTY_REASON)

    for m in _BODY_FILE_VALUE.finditer(cmd):
        path = m.group(1).strip("'\"")
        if path == "-":
            return _out("ask",
                        "This reads the PR body from stdin, which this hook can't "
                        "inspect. Confirm it carries no AI attribution before "
                        "proceeding.")
        try:
            with open(path, encoding="utf-8") as fh:
                if _is_dirty(fh.read()):
                    return _out("deny", f"{_DIRTY_REASON} (in {m.group(1)})")
        except Exception:
            continue
    return None


def _mcp(tool, tool_input):
    if _MCP_MERGE.match(tool):
        return _out("deny",
                    "merge_pull_request writes a commit message server-side, where "
                    "no hook can clean it.")
    if not (_MCP_PR.match(tool) or _MCP_COMMIT.match(tool)
            or _MCP_COMMENT.match(tool) or _MCP_ISSUE.match(tool)):
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


def _arm_alarm():
    """Component A's payload budgets five seconds for a user-supplied pattern
    (install.py:_MAIN). This reads the same `commitcleaner.patterns` file, via
    load_patterns, so it needs the same ceiling: with `^(a+)+b$` in that file, a
    single `gh pr create` burned 24 seconds of CPU without terminating.

    Exiting 0 on fire is the fail-open shape used everywhere else here: saying
    nothing means the tool call proceeds, and component A still cleans the
    commit message itself.
    """
    try:
        def _bail(signum, frame):
            raise SystemExit(0)

        signal.signal(signal.SIGALRM, _bail)
        signal.alarm(5)
    except Exception:
        pass


def main():
    _arm_alarm()
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
