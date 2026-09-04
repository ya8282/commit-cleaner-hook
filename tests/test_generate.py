import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

import install  # noqa: E402
from patterns import DEFAULT_PATTERNS  # noqa: E402

CO = "Co-Authored" + "-By: Claude <noreply@anthropic.com>"


def test_payload_embeds_every_default_pattern():
    """The generated artifact must not drift from patterns.py."""
    payload = install.generate_payload()
    for pat in DEFAULT_PATTERNS:
        assert pat in payload


def test_payload_has_no_plugin_imports():
    payload = install.generate_payload()
    for forbidden in ("from patterns import", "from clean import", "from gitconfig import"):
        assert forbidden not in payload


def test_payload_runs_standalone_and_cleans(tmp_path):
    script = tmp_path / "commit-cleaner.py"
    script.write_text(install.generate_payload())
    msg = tmp_path / "MSG"
    msg.write_text("subject\n\n" + CO + "\n")
    r = subprocess.run([sys.executable, str(script), str(msg)], cwd=tmp_path)
    assert r.returncode == 0
    assert msg.read_text() == "subject\n"


def test_payload_sets_an_alarm():
    assert "signal.alarm" in install.generate_payload()


def test_wrapper_fails_open_on_missing_interpreter():
    assert "command -v python3" in install.WRAPPER
    assert "|| exit 0" in install.WRAPPER
