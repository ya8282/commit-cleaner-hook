import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugins" / "commit-cleaner" / "hooks" / "hooks.json"


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


def test_no_powershell_matcher_paired_with_a_bash_rule():
    """A single `if` rule matches one tool's calls (hooks.md:123)."""
    cfg = json.loads(HOOKS.read_text())
    for handler in cfg["hooks"]["PreToolUse"]:
        if handler.get("if", "").startswith("Bash("):
            assert "PowerShell" not in handler["matcher"]


def test_mcp_matcher_covers_every_tool_guard_py_handles():
    """guard.py's _MCP_PR/_MCP_COMMIT/_MCP_COMMENT/_MCP_MERGE name these nine
    tools; the matcher must fire for all of them or the guard never runs."""
    import re

    cfg = json.loads(HOOKS.read_text())
    mcp_handlers = [
        h for h in cfg["hooks"]["PreToolUse"] if h["matcher"].startswith("mcp__")
    ]
    assert mcp_handlers
    pattern = re.compile(mcp_handlers[0]["matcher"])
    covered = [
        "create_pull_request",
        "update_pull_request",
        "create_or_update_file",
        "delete_file",
        "push_files",
        "merge_pull_request",
        "add_issue_comment",
        "add_comment_to_pending_review",
        "pull_request_review_write",
    ]
    for tool in covered:
        name = f"mcp__github__{tool}"
        assert pattern.match(name), f"{name} not matched by {mcp_handlers[0]['matcher']}"
