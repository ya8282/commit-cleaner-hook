import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import install  # noqa: E402

# The registry-isolation fixture is autouse in tests/conftest.py so it covers
# every module, not just this one.


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    return tmp_path


def test_resolves_default_hooks_dir(tmp_path):
    r = _repo(tmp_path)
    assert install.resolve_hooks_dir(str(r)).name == "hooks"


def test_resolves_custom_hooks_path(tmp_path):
    r = _repo(tmp_path)
    (r / ".husky").mkdir()
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=r, check=True)
    assert install.resolve_hooks_dir(str(r)).name == ".husky"


def test_installs_into_untracked_dir(tmp_path):
    r = _repo(tmp_path)
    ok, _ = install.install_repo(str(r))
    assert ok
    hooks = r / ".git" / "hooks"
    assert (hooks / "commit-msg").exists()
    assert (hooks / "commit-cleaner.py").exists()
    assert (hooks / "commit-msg").stat().st_mode & 0o111


def test_chains_an_existing_hook(tmp_path):
    r = _repo(tmp_path)
    hooks = r / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "commit-msg").write_text("#!/bin/sh\nexit 0\n")
    (hooks / "commit-msg").chmod(0o755)
    install.install_repo(str(r))
    assert (hooks / "commit-msg.chained").exists()
    assert "commit-cleaner" in (hooks / "commit-msg").read_text()


def test_refuses_a_tracked_hooks_dir(tmp_path):
    """A shared hooks dir is team infrastructure. Never edit it silently."""
    r = _repo(tmp_path)
    husky = r / ".husky"
    husky.mkdir()
    (husky / "commit-msg").write_text("#!/bin/sh\nexit 0\n")
    subprocess.run(["git", "add", ".husky/commit-msg"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add husky hook"], cwd=r, check=True)
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=r, check=True)
    assert install.is_tracked(str(r), husky / "commit-msg")
    ok, msg = install.install_repo(str(r))
    assert ok is False
    assert "tracked" in msg.lower()
    assert not (husky / "commit-cleaner.py").exists()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=r,
                            capture_output=True, text=True).stdout
    assert status.strip() == ""


def test_refusal_still_writes_the_payload_inside_dot_git(tmp_path):
    r = _repo(tmp_path)
    husky = r / ".husky"
    husky.mkdir()
    (husky / "commit-msg").write_text("#!/bin/sh\nexit 0\n")
    subprocess.run(["git", "add", ".husky/commit-msg"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add husky hook"], cwd=r, check=True)
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=r, check=True)
    install.install_repo(str(r))
    assert (r / ".git" / "commit-cleaner.py").exists()


def test_upgrade_replaces_a_stale_payload(tmp_path):
    r = _repo(tmp_path)
    install.install_repo(str(r))
    payload = r / ".git" / "hooks" / "commit-cleaner.py"
    payload.write_text("# stale\n")
    install.install_repo(str(r))
    assert "# stale" not in payload.read_text()


def test_uninstall_restores_the_chained_hook(tmp_path):
    r = _repo(tmp_path)
    hooks = r / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "commit-msg").write_text("#!/bin/sh\n# original\nexit 0\n")
    (hooks / "commit-msg").chmod(0o755)
    install.install_repo(str(r))
    install.uninstall_repo(str(r))
    assert "# original" in (hooks / "commit-msg").read_text()
    assert not (hooks / "commit-msg.chained").exists()
    assert not (hooks / "commit-cleaner.py").exists()


def test_registry_falls_back_when_plugin_data_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    # Path.home() reads $HOME on POSIX; point it at a disposable directory so
    # this genuinely exercises the fallback shape without ever computing the
    # developer's real home path.
    monkeypatch.setenv("HOME", str(tmp_path))
    assert install.registry_path() == tmp_path / ".commit-cleaner" / "registry.json"


def test_registry_uses_plugin_data_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    assert str(tmp_path) in str(install.registry_path())


def test_install_records_the_repo_in_the_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    target = tmp_path / "r"
    target.mkdir()
    r = _repo(target)
    install.install_repo(str(r))
    assert str(r) in install.registry_path().read_text()


def test_installs_into_each_submodule(tmp_path, monkeypatch):
    """Submodule commits use .git/modules/<name>/hooks, which a superproject
    install does not reach."""
    sub = tmp_path / "sub"
    sub.mkdir()
    _repo(sub)
    (sub / "s.txt").write_text("s")
    subprocess.run(["git", "add", "s.txt"], cwd=sub, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=sub, check=True)

    top = tmp_path / "top"
    top.mkdir()
    _repo(top)
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", "-q",
         str(sub), "sub"],
        cwd=top, check=True,
    )
    monkeypatch.chdir(top)  # main() resolves the repo from cwd
    install.main(["install.py", "--install"])
    sub_hooks = install.resolve_hooks_dir(str(top / "sub"))
    assert (sub_hooks / "commit-msg").exists()


def test_refuses_when_not_a_git_repo(tmp_path):
    """Never write where you were not invited: a plain directory must not get
    a fabricated .git/hooks."""
    ok, msg = install.install_repo(str(tmp_path))
    assert ok is False
    assert "git repository" in msg.lower()
    assert not (tmp_path / ".git").exists()


def test_no_git_on_path_reports_a_message_not_a_traceback(tmp_path, monkeypatch):
    r = _repo(tmp_path)
    fake_bin = tmp_path / "fakebin"  # empty: no git symlinked into it
    fake_bin.mkdir()
    monkeypatch.setenv("PATH", str(fake_bin))
    ok, msg = install.install_repo(str(r))
    assert ok is False
    assert "git" in msg.lower()


def test_unwritable_hooks_dir_reports_a_message_not_a_traceback(tmp_path):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores directory write permissions")
    r = _repo(tmp_path)
    hooks = r / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hooks.chmod(0o500)
    try:
        ok, msg = install.install_repo(str(r))
    finally:
        hooks.chmod(0o700)  # restore so pytest can clean up tmp_path
    assert ok is False
    assert msg
