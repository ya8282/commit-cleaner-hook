"""The wire boundary: both scripts run as real processes, JSON in, JSON out.

decide() had thirty direct tests and main() had none, so deleting the
`print(json.dumps(...))` from either entry point left the suite green: the
plugin could have been wholly inert in production and CI would have passed.
Everything here therefore goes through a subprocess and asserts on bytes
actually written to stdout, never on an imported function's return value.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import install  # noqa: E402

CO = "Co-Authored" + "-By: Claude <noreply@anthropic.com>"


def _run(script, stdin_text, cwd=None, env=None, argv0_is_script=False):
    """Run one of the hook scripts exactly as Claude Code would."""
    target = str(PLUGIN / script)
    cmd = [target] if argv0_is_script else [sys.executable, target]
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(
        cmd, input=stdin_text, text=True, capture_output=True,
        cwd=str(cwd) if cwd else None, env=e, timeout=30,
    )


def _bash_payload(command):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": os.getcwd(),
        "session_id": "test",
    })


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    return tmp_path


# --- guard.py -----------------------------------------------------------


def test_guard_emits_a_deny_envelope_on_stdout(tmp_path):
    """The whole point of the process: a decision reaches stdout in the
    envelope the PreToolUse protocol requires."""
    out = _run("guard.py", _bash_payload(
        'gh pr create --title t --body "summary' + chr(10) * 2 + CO + '"'
    ), cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    body = json.loads(out.stdout)
    hso = body["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"]


def test_guard_emits_a_deny_for_no_verify(tmp_path):
    out = _run("guard.py", _bash_payload("git commit --no-verify -m x"), cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    hso = json.loads(out.stdout)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"


def test_guard_emits_an_ask_envelope(tmp_path):
    out = _run("guard.py", json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/Users/x/proj/.git/hooks/commit-msg",
                       "content": ""},
    }), cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_guard_says_nothing_for_a_clean_command(tmp_path):
    """Silence is the allow path. Anything on stdout here would be a bug."""
    out = _run("guard.py", _bash_payload('git commit -m "feat: normal"'), cwd=tmp_path)
    assert out.returncode == 0
    assert out.stdout == ""


def test_guard_runs_under_its_own_shebang(tmp_path):
    """hooks.json spawns the file itself, not `python3 guard.py`, so the exec
    bit and the shebang are part of the contract."""
    assert os.access(str(PLUGIN / "guard.py"), os.X_OK)
    out = _run("guard.py", _bash_payload("git commit --no-verify -m x"),
               cwd=tmp_path, argv0_is_script=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_guard_malformed_json_exits_zero_with_no_output(tmp_path):
    """Spec: malformed JSON on stdin -> exit 0, no output."""
    out = _run("guard.py", "{not json at all", cwd=tmp_path)
    assert out.returncode == 0
    assert out.stdout == ""


def test_guard_empty_stdin_exits_zero_with_no_output(tmp_path):
    out = _run("guard.py", "", cwd=tmp_path)
    assert out.returncode == 0
    assert out.stdout == ""


def test_guard_pathological_user_pattern_costs_five_seconds_not_the_call(tmp_path):
    """guard.py reads the same user-supplied commitcleaner.patterns file that
    component A guards with signal.alarm(5). Without the same alarm, one
    `gh pr create` burned 24 seconds of CPU without terminating."""
    r = _repo(tmp_path)
    pat = r / "patterns.txt"
    pat.write_text("^(a+)+b$\n")
    subprocess.run(["git", "config", "commitcleaner.patterns", str(pat)],
                   cwd=r, check=True)
    start = time.time()
    out = _run("guard.py", _bash_payload(
        'gh pr create --title t --body "' + "a" * 70 + '"'
    ), cwd=r)
    elapsed = time.time() - start
    assert out.returncode == 0
    assert out.stdout == ""
    assert elapsed < 15, f"alarm did not fire: {elapsed:.1f}s"


# --- check_install.py ---------------------------------------------------


def test_check_install_warns_over_the_wire(tmp_path):
    r = _repo(tmp_path)
    out = _run("check_install.py", json.dumps({
        "hook_event_name": "SessionStart", "source": "startup",
    }), cwd=r, env={"CLAUDE_PROJECT_DIR": str(r)})
    assert out.returncode == 0, out.stderr
    assert "not installed" in json.loads(out.stdout)["systemMessage"]


def test_check_install_is_silent_when_the_hook_is_alive(tmp_path):
    r = _repo(tmp_path)
    install.install_repo(str(r))
    out = _run("check_install.py", json.dumps({"hook_event_name": "SessionStart"}),
               cwd=r, env={"CLAUDE_PROJECT_DIR": str(r)})
    assert out.returncode == 0
    assert out.stdout == ""


def test_check_install_malformed_json_exits_zero_with_no_output(tmp_path):
    """Same contract as guard.py: a broken payload must not produce output or
    a non-zero exit, either of which would surface as a session-start error."""
    out = _run("check_install.py", "{not json at all", cwd=tmp_path,
               env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert out.returncode == 0
    assert out.stdout == ""


def test_check_install_runs_under_its_own_shebang(tmp_path):
    r = _repo(tmp_path)
    assert os.access(str(PLUGIN / "check_install.py"), os.X_OK)
    out = _run("check_install.py", json.dumps({"hook_event_name": "SessionStart"}),
               cwd=r, env={"CLAUDE_PROJECT_DIR": str(r)}, argv0_is_script=True)
    assert out.returncode == 0, out.stderr
    assert "systemMessage" in json.loads(out.stdout)
