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


# --- Fix round 1: merge false positive (Important 1) ---


def test_gh_pr_edit_mentioning_merge_in_body_allowed():
    """`edit` is the real subcommand; the mention of `pr merge` sits inside
    the quoted body text and must not self-trigger the merge guard."""
    d = bash('gh pr edit 3 --body "See also gh pr merge --squash for background."')
    assert d is None


def test_gh_pr_create_documenting_merge_body_flag_allowed():
    d = bash(
        'gh pr create --body "docs: explain gh pr merge --squash --body flag usage"'
    )
    assert d is None


def test_gh_pr_merge_with_body_still_denied():
    """The genuine case: subcommand really is `pr merge`, --body really is a
    flag on it, not text inside a quoted body. Component A does not cover
    this path (no commit-msg hook runs for a server-side merge commit)."""
    d = bash('gh pr merge 3 --squash --body "x"')
    assert d["permissionDecision"] == "deny"


# --- Fix round 1: unquoted --body= (Important 2) ---


def test_unquoted_dirty_body_denied():
    # No space after the colon: a real unquoted shell token can't contain one.
    trailer = "Claude-Sess" + "ion:" + "https://claude.ai/code/session_abc"
    d = bash(f"gh pr create --title t --body={trailer}")
    assert d["permissionDecision"] == "deny"


def test_unquoted_clean_body_allowed():
    assert bash("gh pr create --title t --body=hello") is None


def test_body_that_is_only_a_trailer_is_denied():
    """clean() deliberately leaves a message that is ONLY a trailer
    untouched (it never empties a real commit message). A PR body has no
    such floor, so this must still be caught."""
    trailer = "Co-Authored" + "-By: Claude <noreply@anthropic.com>"
    assert bash(f'gh pr create --body "{trailer}"')["permissionDecision"] == "deny"


# --- Fix round 1: gap (a), MCP review/comment tools ---


def test_mcp_add_issue_comment_dirty_denied():
    d = guard.decide({
        "tool_name": "mcp__github__add_issue_comment",
        "tool_input": {"issue_number": 3, "body": "thanks\n\n" + CO},
    })
    assert d["permissionDecision"] == "deny"


def test_mcp_add_comment_to_pending_review_dirty_denied():
    d = guard.decide({
        "tool_name": "mcp__github__add_comment_to_pending_review",
        "tool_input": {"path": "a.py", "body": "nit\n\n" + SESS},
    })
    assert d["permissionDecision"] == "deny"


def test_mcp_pull_request_review_write_dirty_denied():
    d = guard.decide({
        "tool_name": "mcp__github__pull_request_review_write",
        "tool_input": {"method": "create", "body": "lgtm\n\n" + CO},
    })
    assert d["permissionDecision"] == "deny"


def test_unrelated_mcp_comment_tool_untouched():
    assert guard.decide({
        "tool_name": "mcp__github__list_issue_comments", "tool_input": {}
    }) is None


# --- Fix round 1: gap (b), --body-file - (stdin) ---


def test_body_file_stdin_asks():
    d = bash("gh pr create --body-file -")
    assert d["permissionDecision"] == "ask"


# --- Fix wave 2: gh short flags (Important 1) ---
# gh's own --help lists the short form first, so a model reaching for `-b`
# is doing the ordinary thing, not evading. Matching only `--body` left all
# of B2 bypassable by typing two fewer characters.


def test_short_body_flag_on_pr_create_denied():
    d = bash('gh pr create --title t -b "summary\n\n' + CO + '"')
    assert d["permissionDecision"] == "deny"


def test_short_body_flag_on_pr_edit_denied():
    d = bash('gh pr edit 3 -b "summary\n\n' + SESS + '"')
    assert d["permissionDecision"] == "deny"


def test_short_body_flag_with_equals_denied():
    trailer = "Claude-Sess" + "ion:" + "https://claude.ai/code/session_abc"
    d = bash(f"gh pr create --title t -b={trailer}")
    assert d["permissionDecision"] == "deny"


def test_short_body_flag_clean_allowed():
    assert bash('gh pr create --title t -b "a clean summary"') is None


def test_short_body_file_flag_denied(tmp_path):
    """-F is --body-file for gh pr create/edit."""
    f = tmp_path / "body.md"
    f.write_text("summary\n\n" + CO + "\n")
    d = bash(f"gh pr create -F {f}")
    assert d["permissionDecision"] == "deny"


def test_short_body_file_flag_clean_allowed(tmp_path):
    f = tmp_path / "body.md"
    f.write_text("just a summary\n")
    assert bash(f"gh pr create -F {f}") is None


def test_short_body_file_stdin_asks():
    """A bare `-` still means stdin, which the hook cannot inspect."""
    d = bash("gh pr create -F -")
    assert d["permissionDecision"] == "ask"


def test_pr_merge_with_short_flags_denied():
    d = bash('gh pr merge --squash -b "x" -t "y"')
    assert d["permissionDecision"] == "deny"


def test_pr_merge_with_short_subject_only_denied():
    d = bash('gh pr merge 3 --squash -t "subject"')
    assert d["permissionDecision"] == "deny"


def test_pr_merge_with_body_file_denied(tmp_path):
    """--body-file writes the same server-side commit message --body does."""
    f = tmp_path / "body.md"
    f.write_text("just a summary\n")
    d = bash(f"gh pr merge 3 --squash --body-file {f}")
    assert d["permissionDecision"] == "deny"


def test_plain_pr_merge_still_allowed():
    assert bash("gh pr merge 3 --squash") is None
    assert bash("gh pr merge 3 --squash --delete-branch") is None


def test_second_body_flag_is_checked_too():
    """Extraction walks every match, so the decision does not hinge on which
    flag happens to come first on the command line."""
    d = bash('gh pr create -t "title" --body "summary\n\n' + CO + '"')
    assert d["permissionDecision"] == "deny"


def test_issue_create_with_short_body_denied():
    """_gh matches `gh (pr|issue)`, so issues are in scope for the CLI."""
    d = bash('gh issue create --title t -b "report\n\n' + CO + '"')
    assert d["permissionDecision"] == "deny"
