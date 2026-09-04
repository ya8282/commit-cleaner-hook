import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import check_install  # noqa: E402
import install  # noqa: E402


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_installed_and_executable_is_silent(tmp_path):
    r = _repo(tmp_path)
    install.install_repo(str(r))
    assert check_install.status(str(r)) is None


def test_not_installed_warns(tmp_path):
    r = _repo(tmp_path)
    assert "not installed" in check_install.status(str(r))


def test_the_suggested_command_is_one_you_can_actually_run(tmp_path, monkeypatch):
    """A literal ${CLAUDE_PLUGIN_ROOT} in the message expands to nothing when
    pasted, so the reader is told to run `python3 /install.py`. This hook runs
    where the variable is set, so it resolves the path itself."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugins/commit-cleaner@v1")
    r = _repo(tmp_path)
    warning = check_install.status(str(r))
    assert "${CLAUDE_PLUGIN_ROOT}" not in warning
    assert "python3 /plugins/commit-cleaner@v1/install.py" in warning


def test_the_suggested_command_falls_back_to_the_slash_command(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    r = _repo(tmp_path)
    assert "/commit-cleaner-install" in check_install.status(str(r))


def test_present_but_not_executable_warns(tmp_path):
    r = _repo(tmp_path)
    install.install_repo(str(r))
    hook = r / ".git" / "hooks" / "commit-msg"
    hook.chmod(0o644)
    assert "executable" in check_install.status(str(r))


def test_custom_hooks_path_is_resolved(tmp_path):
    r = _repo(tmp_path)
    (r / "myhooks").mkdir()
    subprocess.run(["git", "config", "core.hooksPath", "myhooks"], cwd=r, check=True)
    install.install_repo(str(r))
    assert check_install.status(str(r)) is None


def test_outside_a_repo_is_silent(tmp_path):
    assert check_install.status(str(tmp_path)) is None


def test_registry_is_isolated_from_the_real_home():
    """This module calls install_repo(), which records into the registry. The
    autouse fixture in conftest.py must be redirecting that away from the
    developer's real ~/.commit-cleaner/registry.json -- it once was not, and
    three entries landed there for real."""
    assert str(Path.home()) not in str(install.registry_path())
