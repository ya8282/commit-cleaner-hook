import sys
from pathlib import Path

import pytest

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


def test_prose_mentioning_sh_c_is_not_matched():
    """A commit message that mentions sh -c must not trigger the unwrapper."""
    assert bash('git commit -m "docs: explain why sh -c bypasses guards"') is None


def test_shell_wrapper_forms_denied():
    """bash/sh/zsh -c and eval hand a quoted argument to a nested shell;
    the guard has to look inside, not just at the outer command name."""
    assert dec('bash -c "git commit --no-verify -m x"') == "deny"
    assert dec('sh -c "git commit --no-verify -m x"') == "deny"
    assert dec('zsh -c "git commit --no-verify -m x"') == "deny"
    assert dec('eval "git commit --no-verify -m x"') == "deny"


def test_shell_wrapper_single_quoted_denied():
    assert dec("bash -c 'git commit --no-verify -m x'") == "deny"
    assert dec("eval 'git commit --no-verify -m x'") == "deny"


def test_backtick_form_denied():
    assert dec("`git commit --no-verify -m x`") == "deny"


def test_shell_wrapper_with_clean_commit_untouched():
    """The wrapper must not make an otherwise-clean commit look dangerous."""
    assert bash("bash -c \"git commit -m 'feat: a normal commit'\"") is None


@pytest.mark.xfail(
    reason="B1 unwraps a closed set of shell wrappers (bash/sh/zsh/dash -c, "
    "eval); arbitrary $(...) command substitution is an unbounded pattern "
    "that is out of scope for accidental-attribution defense. See _unwrap's "
    "docstring in guard.py."
)
def test_command_substitution_is_a_documented_limit():
    """$(...) indirection is parked deliberately -- see _unwrap's docstring."""
    assert dec("$(echo git commit --no-verify -m x)") == "deny"


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


# --- Fix wave 2: flag search scoped to the git commit invocation ---
# `-n` belongs to whichever command it was typed after. Searching the whole
# command string denied three ordinary compound shapes, and the deny text
# blamed --no-verify, so the obvious retry was the same command again.


def test_dash_n_on_a_different_git_subcommand_allowed():
    assert bash('git add -n . && git commit -m "wip"') is None
    assert bash('git log -n 5; git commit -m "y"') is None


def test_dash_n_on_a_later_non_git_command_allowed():
    assert bash('git commit -m "x" && npm run build -- -n') is None
    assert bash('git commit -m "x" | tee -a log; grep -n foo log') is None


def test_env_prefix_on_a_different_command_allowed():
    """The assignment belongs to npm, not to the commit after it."""
    assert bash('HOME=/tmp npm test && git commit -m "x"') is None


def test_hookspath_flag_on_a_different_git_invocation_allowed():
    assert bash('git -c core.hooksPath=/dev/null status; git commit -m "x"') is None


def test_no_verify_in_a_compound_command_still_denied():
    """Scoping must not lose the true positive it was scoped around."""
    assert dec('git add . && git commit --no-verify -m "x"') == "deny"
    assert dec('git add -n .; git commit -nm x') == "deny"


def test_deny_text_names_the_flag_that_triggered_it():
    """A message that blames --no-verify when the model typed -nm invites the
    same retry. It has to name what was actually matched."""
    assert "-nm" in bash("git commit -nm x")["permissionDecisionReason"]
    assert "--no-verif" in bash("git commit --no-verif -m x")["permissionDecisionReason"]


def test_notebook_edit_into_git_hooks_asks():
    """NotebookEdit names its target notebook_path, not file_path."""
    d = guard.decide({
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": "/Users/x/proj/.git/hooks/commit-msg.ipynb"},
    })
    assert d["permissionDecision"] == "ask"


def test_ordinary_notebook_edit_untouched():
    d = guard.decide({
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": "/Users/x/proj/analysis.ipynb"},
    })
    assert d is None


def test_powershell_commands_are_decided_too():
    """decide() dispatches PowerShell, and hooks.json now matches it."""
    assert dec("git commit --no-verify -m x") == "deny"
    d = guard.decide({
        "tool_name": "PowerShell",
        "tool_input": {"command": "git commit --no-verify -m x"},
    })
    assert d["permissionDecision"] == "deny"
