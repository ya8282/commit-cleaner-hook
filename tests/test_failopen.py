"""Component A must never block a commit. Seven ways it could, all checked."""
import os
import stat
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import install  # noqa: E402

CO = "Co-Authored" + "-By: Claude <noreply@anthropic.com>"


def _repo(tmp_path, payload):
    """A repo with the wrapper installed and a payload of our choosing."""
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "commit-msg").write_text(install.WRAPPER)
    (hooks / "commit-msg").chmod(0o755)
    (hooks / "commit-cleaner.py").write_text(payload)
    (tmp_path / "f").write_text("a")
    subprocess.run(["git", "add", "f"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(repo, subject, env=None):
    msg = subject + "\n\n" + CO + "\n"
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(
        ["git", "commit", "-q", "-F", "-"],
        cwd=repo, input=msg, text=True, capture_output=True, env=e, timeout=30,
    )


def _head(repo):
    return subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], cwd=repo, capture_output=True, text=True
    ).stdout


def test_control_cleans(tmp_path):
    r = _repo(tmp_path, install.generate_payload())
    assert _commit(r, "control").returncode == 0
    assert "anthropic.com" not in _head(r)


def test_syntax_error_still_commits(tmp_path):
    r = _repo(tmp_path, "def broken(:\n")
    assert _commit(r, "syntaxerr").returncode == 0
    assert "anthropic.com" in _head(r)


def test_runtime_exception_still_commits(tmp_path):
    r = _repo(tmp_path, "raise RuntimeError('boom')\n")
    assert _commit(r, "runtimeerr").returncode == 0


def test_sigkill_still_commits(tmp_path):
    r = _repo(tmp_path, "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n")
    assert _commit(r, "sigkill").returncode == 0


def test_missing_payload_still_commits(tmp_path):
    r = _repo(tmp_path, install.generate_payload())
    (r / ".git" / "hooks" / "commit-cleaner.py").unlink()
    assert _commit(r, "missingfile").returncode == 0


def test_non_executable_wrapper_still_commits(tmp_path):
    r = _repo(tmp_path, install.generate_payload())
    hook = r / ".git" / "hooks" / "commit-msg"
    hook.chmod(hook.stat().st_mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH)
    assert _commit(r, "notexec").returncode == 0


def test_no_python3_on_path_still_commits(tmp_path):
    r = _repo(tmp_path, install.generate_payload())
    # git and python3 are often colocated (Homebrew, /usr/bin on Linux), so
    # narrowing PATH to git's own directory does not reliably hide python3.
    # Build a bin dir containing only a symlink to the real git instead: git
    # resolves its own libexec helpers via its compiled-in exec-path, not
    # PATH, so subcommands still work while python3 is genuinely absent.
    import shutil

    git_bin = shutil.which("git")
    assert git_bin, "git must be on PATH for this test"
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    (fake_bin / "git").symlink_to(git_bin)
    assert shutil.which("python3", path=str(fake_bin)) is None, (
        "python3 is resolvable under the narrowed PATH; isolation failed"
    )
    assert shutil.which("git", path=str(fake_bin)) is not None, (
        "git is not resolvable under the narrowed PATH; the test would prove nothing"
    )
    env = {"PATH": str(fake_bin)}
    out = _commit(r, "nopython", env=env)
    assert out.returncode == 0
    # A missing interpreter must degrade to a no-op, not silently drop the
    # hook: the trailer should survive untouched.
    assert "anthropic.com" in _head(r)


def test_hanging_payload_is_killed_by_alarm_and_commits(tmp_path):
    """The failure mode the shell wrapper alone cannot cover."""
    r = _repo(tmp_path, install.generate_payload().replace(
        "    if len(argv) < 2:", "    import time; time.sleep(60)\n    if len(argv) < 2:"
    ))
    out = _commit(r, "hang")
    assert out.returncode == 0


def test_chained_hook_still_blocks(tmp_path):
    """The one permitted block: a third-party hook we chained."""
    r = _repo(tmp_path, install.generate_payload())
    chained = r / ".git" / "hooks" / "commit-msg.chained"
    chained.write_text("#!/bin/sh\nexit 1\n")
    chained.chmod(0o755)
    assert _commit(r, "chained-rejects").returncode != 0
