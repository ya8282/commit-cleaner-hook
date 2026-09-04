import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "commit-cleaner"
HOOKS = PLUGIN / "hooks" / "hooks.json"
sys.path.insert(0, str(PLUGIN))

import guard  # noqa: E402


def test_hooks_json_parses():
    json.loads(HOOKS.read_text())


def test_every_handler_has_one_if_rule_and_a_timeout():
    """`if` holds exactly one permission rule (hooks.md:432), and the default
    command timeout is 600s, which is never what a guard wants."""
    cfg = json.loads(HOOKS.read_text())
    for handler in cfg["hooks"]["PreToolUse"]:
        assert "matcher" in handler
        if "if" in handler:
            assert "&&" not in handler["if"] and "||" not in handler["if"]
        for h in handler["hooks"]:
            assert h["timeout"] <= 10


def test_referenced_scripts_exist():
    cfg = json.loads(HOOKS.read_text())
    for event in cfg["hooks"].values():
        for handler in event:
            for h in handler["hooks"]:
                rel = h["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "")
                assert (ROOT / "plugins" / "commit-cleaner" / rel).exists()


def test_the_bash_handler_has_no_if_filter():
    """`if` is narrower than guard.py, so it must not gate the Bash handler.

    hooks.md's Bash matching table (the `bash-if-matching` section) says
    `Bash(git *)` matches `FOO=bar git push` (leading assignments are
    stripped), `npm test && git push` (each subcommand is checked), and
    commands inside `$()` or backticks. It says nothing that would make it
    match `/usr/bin/git`, `command git`, `\\git`, `env FOO=1 git`,
    `rtk git`, or `bash -c "git commit --no-verify"` -- in each of those the
    command name is not `git`. Those are exactly the forms B1 exists to
    catch, so gating on `Bash(git *)` left the guard dead in production for
    every evasion it was written for. The same table's closing note is
    explicit: the `if` filter is best-effort, so use the permission system
    rather than a hook to enforce a hard allow or deny.

    The cost is one interpreter spawn per Bash call; guard.py returns None
    for anything it does not recognise. The matcher is anchored so the spawn
    does not also happen on BashOutput.
    """
    cfg = json.loads(HOOKS.read_text())
    bash_handlers = [
        h for h in cfg["hooks"]["PreToolUse"] if "Bash" in h["matcher"]
    ]
    assert bash_handlers
    for h in bash_handlers:
        assert "if" not in h, "an `if` here re-introduces the production-dead guard"
        assert h["matcher"].startswith("^") and h["matcher"].endswith("$")


def test_every_tool_decide_dispatches_has_a_handler():
    """decide() branching on a tool that no matcher selects is a branch that
    can never run in production -- which is what NotebookEdit was."""
    cfg = json.loads(HOOKS.read_text())
    matchers = [re.compile(h["matcher"]) for h in cfg["hooks"]["PreToolUse"]]
    for tool in ("Bash", "PowerShell", "Write", "Edit", "NotebookEdit"):
        assert any(m.search(tool) for m in matchers), f"{tool} has no handler"


def test_no_powershell_matcher_paired_with_a_bash_rule():
    """A single `if` rule matches one tool's calls (hooks.md:123)."""
    cfg = json.loads(HOOKS.read_text())
    for handler in cfg["hooks"]["PreToolUse"]:
        if handler.get("if", "").startswith("Bash("):
            assert "PowerShell" not in handler["matcher"]


def _guard_mcp_regexes():
    """Every _MCP_* regex guard.py defines, found by introspection.

    Derived, never listed. The previous version of this test hardcoded nine
    tool names, so adding a tenth to guard.py and forgetting hooks.json --
    which makes the guard dead in production for that tool -- kept the test
    green. A list that has to be edited alongside the thing it checks is not
    an invariant.
    """
    return {
        name: value
        for name, value in vars(guard).items()
        if name.startswith("_MCP_") and hasattr(value, "pattern")
    }


def _names_in(pattern, source):
    """The tool names out of a `mcp__.*__(a|b|c)` alternation."""
    m = re.search(r"mcp__\\?\.\*__\(?([\w|]+)\)?\$?$", pattern)
    assert m, f"{source} no longer has the shape this test derives names from: {pattern}"
    return set(m.group(1).split("|"))


def _mcp_matcher():
    cfg = json.loads(HOOKS.read_text())
    handlers = [
        h for h in cfg["hooks"]["PreToolUse"] if h["matcher"].startswith("mcp__")
    ]
    assert len(handlers) == 1, "one MCP handler, or these two checks miss a matcher"
    return handlers[0]["matcher"]


def test_mcp_matcher_covers_every_tool_guard_py_handles():
    """A tool guard.py decides on but hooks.json does not match is a guard
    that never runs. Both sides are derived from the code."""
    matcher = re.compile(_mcp_matcher())
    for attr, regex in _guard_mcp_regexes().items():
        for tool in _names_in(regex.pattern, attr):
            name = f"mcp__github__{tool}"
            assert matcher.match(name), f"{name} ({attr}) is not matched by hooks.json"


def test_mcp_matcher_names_no_tool_guard_py_ignores():
    """The other direction: a matcher wider than the guard spawns a process
    that can only ever decide nothing."""
    guard_regexes = list(_guard_mcp_regexes().values())
    for tool in _names_in(_mcp_matcher(), "hooks.json matcher"):
        name = f"mcp__github__{tool}"
        assert any(r.match(name) for r in guard_regexes), \
            f"{name} is matched by hooks.json but no _MCP_* regex in guard.py"
