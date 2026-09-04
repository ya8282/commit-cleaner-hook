"""Proves the test runner and import path work before anything real exists."""
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))


def test_plugin_dir_exists():
    assert PLUGIN.is_dir()


def test_python_floor():
    assert sys.version_info >= (3, 9)
