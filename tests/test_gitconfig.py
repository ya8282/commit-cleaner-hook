import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

from clean import clean  # noqa: E402
from gitconfig import load_patterns  # noqa: E402

CO = "Co-Authored" + "-By: Claude <noreply@anthropic.com>"


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_defaults_when_no_config(tmp_path):
    _repo(tmp_path)
    assert clean(CO + "\nkeep\n", load_patterns(str(tmp_path))) == "keep\n"


def test_extra_pattern_file_extends_defaults(tmp_path):
    _repo(tmp_path)
    pf = tmp_path / "pats.txt"
    pf.write_text("# a comment\n\n^DROPME$\n")
    subprocess.run(
        ["git", "config", "commitcleaner.patterns", str(pf)], cwd=tmp_path, check=True
    )
    pats = load_patterns(str(tmp_path))
    assert clean("DROPME\n" + CO + "\nkeep\n", pats) == "keep\n"


def test_defaults_false_uses_only_the_file(tmp_path):
    _repo(tmp_path)
    pf = tmp_path / "pats.txt"
    pf.write_text("^DROPME$\n")
    subprocess.run(
        ["git", "config", "commitcleaner.patterns", str(pf)], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "commitcleaner.defaults", "false"], cwd=tmp_path, check=True
    )
    pats = load_patterns(str(tmp_path))
    assert clean("DROPME\n" + CO + "\n", pats) == CO + "\n"


def test_missing_pattern_file_falls_back_to_defaults(tmp_path):
    _repo(tmp_path)
    subprocess.run(
        ["git", "config", "commitcleaner.patterns", str(tmp_path / "nope.txt")],
        cwd=tmp_path,
        check=True,
    )
    assert clean(CO + "\nkeep\n", load_patterns(str(tmp_path))) == "keep\n"


def test_outside_a_repo_returns_defaults(tmp_path):
    assert clean(CO + "\nkeep\n", load_patterns(str(tmp_path))) == "keep\n"
