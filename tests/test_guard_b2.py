import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import guard  # noqa: E402

CO = "Co-Authored" + "-By: Claude <noreply@anthropic.com>"
SESS = "Claude-Sess" + "ion: https://claude.ai/code/session_abc"


def bash(cmd):
    return guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}})


def test_dirty_pr_body_denied():
    d = bash('gh pr create --title t --body "summary\n\n' + CO + '"')
    assert d["permissionDecision"] == "deny"


def test_dirty_session_trailer_in_body_denied():
    d = bash('gh pr edit 3 --body "summary\n\n' + SESS + '"')
    assert d["permissionDecision"] == "deny"


def test_clean_pr_body_allowed():
    assert bash('gh pr create --title t --body "a clean summary"') is None


def test_body_file_is_read_and_denied_when_dirty(tmp_path):
    f = tmp_path / "body.md"
    f.write_text("summary\n\n" + CO + "\n")
    d = bash(f"gh pr create --body-file {f}")
    assert d["permissionDecision"] == "deny"


def test_body_file_clean_is_allowed(tmp_path):
    f = tmp_path / "body.md"
    f.write_text("just a summary\n")
    assert bash(f"gh pr create --body-file {f}") is None


def test_missing_body_file_says_nothing(tmp_path):
    assert bash(f"gh pr create --body-file {tmp_path}/nope.md") is None


def test_fill_is_allowed():
    """--fill takes the body from commits, which component A already cleaned."""
    assert bash("gh pr create --fill") is None


def test_pr_merge_with_body_denied():
    d = bash('gh pr merge 3 --squash --body "x"')
    assert d["permissionDecision"] == "deny"


def test_unrelated_gh_command_untouched():
    assert bash("gh pr list") is None
    assert bash("gh repo view") is None


def test_mcp_create_pull_request_dirty_denied():
    d = guard.decide({
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"title": "t", "body": "summary\n\n" + CO},
    })
    assert d["permissionDecision"] == "deny"


def test_mcp_create_pull_request_clean_allowed():
    d = guard.decide({
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"title": "t", "body": "clean"},
    })
    assert d is None


def test_mcp_renamed_server_prefix_still_matched():
    d = guard.decide({
        "tool_name": "mcp__plugin_gh_github-remote__create_or_update_file",
        "tool_input": {"path": "a.txt", "message": "subject\n\n" + CO},
    })
    assert d["permissionDecision"] == "deny"


def test_mcp_merge_pull_request_denied():
    d = guard.decide({
        "tool_name": "mcp__github__merge_pull_request",
        "tool_input": {"pullNumber": 3, "commit_title": "x"},
    })
    assert d["permissionDecision"] == "deny"


def test_unrelated_mcp_tool_untouched():
    assert guard.decide({
        "tool_name": "mcp__github__list_pull_requests", "tool_input": {}
    }) is None
