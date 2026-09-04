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
    assert "commit-cleaner install" in check_install.status(str(r))


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
