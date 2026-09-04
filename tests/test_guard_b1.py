import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import guard  # noqa: E402


def bash(cmd):
    return guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}})


def dec(cmd):
    d = bash(cmd)
    return d["permissionDecision"] if d else None


def test_no_verify_denied():
    assert dec("git commit --no-verify -m x") == "deny"


def test_abbreviated_no_verify_denied():
    """git accepts unambiguous long-option prefixes; --no-verif commits."""
    assert dec("git commit --no-verif -m x") == "deny"
    assert dec("git commit --no-veri -m x") == "deny"


def test_short_flag_cluster_denied():
    assert dec("git commit -nm x") == "deny"
    assert dec("git commit -n -m x") == "deny"


def test_inline_hookspath_denied():
    assert dec("git -c core.hooksPath=/dev/null commit -m x") == "deny"


def test_env_prefixes_denied():
    assert dec("GIT_CONFIG_GLOBAL=/dev/null git commit -m x") == "deny"
    assert dec("HOME=/tmp git commit -m x") == "deny"
    assert dec("HUSKY=0 git commit -m x") == "deny"


def test_absolute_path_and_wrapper_forms_denied():
    assert dec("/usr/bin/git commit --no-verify -m x") == "deny"
    assert dec("command git commit --no-verify -m x") == "deny"
    assert dec("env FOO=1 git commit --no-verify -m x") == "deny"
    assert dec("rtk git commit --no-verify -m x") == "deny"


def test_persisted_hookspath_asks_not_denies():
    """husky init runs exactly this. Denying it would break setup."""
    assert dec("git config core.hooksPath .husky") == "ask"


def test_chmod_and_rm_against_the_hook_denied():
    assert dec("chmod -x .git/hooks/commit-msg") == "deny"
    assert dec("rm .git/hooks/commit-msg") == "deny"
    assert dec("rm -f .husky/commit-msg") == "deny"


def test_clean_commit_untouched():
    assert bash('git commit -m "feat: a normal commit"') is None


def test_unrelated_commands_untouched():
    assert bash("chmod +x scripts/build.sh") is None
    assert bash("rm -rf node_modules") is None
    assert bash("git status") is None


def test_prose_about_git_is_not_matched():
    """A commit message ABOUT --no-verify must not be read as running it."""
    assert bash('git commit -m "docs: explain why --no-verify is banned"') is None


def test_write_into_git_hooks_asks():
    d = guard.decide({
        "tool_name": "Write",
        "tool_input": {"file_path": "/Users/x/proj/.git/hooks/commit-msg", "content": ""},
    })
    assert d["permissionDecision"] == "ask"


def test_edit_of_git_config_asks():
    d = guard.decide({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/Users/x/proj/.git/config"},
    })
    assert d["permissionDecision"] == "ask"


def test_ordinary_file_edit_untouched():
    d = guard.decide({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/Users/x/proj/src/main.py"},
    })
    assert d is None


def test_malformed_payload_returns_none():
    assert guard.decide({}) is None
    assert guard.decide({"tool_name": "Bash", "tool_input": {}}) is None
