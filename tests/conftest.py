"""Suite-wide fixtures.

The registry isolation lives here, not in one test module, because anything
that reaches `install.install_repo()` writes into the developer's real
`~/.commit-cleaner/registry.json`. That happened: the fixture was originally
local to `tests/test_install.py`, `tests/test_check_install.py` called
`install_repo()` three times without it, and the real registry grew by three
entries. A conftest fixture covers every test file, including ones not written
yet, so the same regression cannot come back through a new module.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch, tmp_path_factory):
    """Point CLAUDE_PLUGIN_DATA at a disposable directory, unrelated to any
    test's own tmp_path so it never shows up as an untracked file in a test
    repo's git status.

    Tests that deliberately exercise the set/unset registry-path behaviour
    override this within their own body.
    """
    registry_dir = tmp_path_factory.mktemp("registry")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(registry_dir))
