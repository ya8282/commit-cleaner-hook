#!/usr/bin/env python3
"""Generates and installs the self-contained commit-msg payload.

The installed copy must run with no plugin present, and ${CLAUDE_PLUGIN_ROOT}
is versioned and garbage-collected, so a hook pointing into it would become a
dangling path — which blocks commits. Hence: inline, copy, stamp a version.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.1.0"
HERE = Path(__file__).resolve().parent

WRAPPER = f"""#!/bin/sh
# commit-cleaner {VERSION} - fails open by construction.
# Any failure of the cleaner must still let the commit through.
d=$(dirname "$0")
if command -v python3 >/dev/null 2>&1; then
    python3 "$d/commit-cleaner.py" "$@" || exit 0
fi
# A pre-existing hook was moved aside at install time. It is the one thing
# permitted to block: a repo's commitlint must still reject a bad message.
if [ -x "$d/commit-msg.chained" ]; then
    exec "$d/commit-msg.chained" "$@"
fi
exit 0
"""

_MAIN = '''

# ---- entry point -----------------------------------------------------------
def main(argv):
    # A catastrophically backtracking user pattern must cost 5 seconds, not the
    # commit. git applies no hook timeout, and timeout(1) is absent on macOS.
    try:
        import signal

        def _bail(signum, frame):
            raise SystemExit(0)

        signal.signal(signal.SIGALRM, _bail)
        signal.alarm(5)
    except Exception:
        pass

    if len(argv) < 2:
        return 0
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            original = fh.read()
        result = clean(original, load_patterns(os.getcwd()))
        if result != original:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(result)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv))
'''


def _module_body(name):
    # type: (str) -> str
    """Source of a sibling module with its own imports of siblings removed."""
    text = (HERE / name).read_text(encoding="utf-8")
    keep = []
    for line in text.splitlines():
        if line.startswith(("from patterns import", "from clean import", "from gitconfig import")):
            continue
        keep.append(line)
    return "\n".join(keep)


def generate_payload():
    # type: () -> str
    header = (
        "#!/usr/bin/env python3\n"
        f'"""commit-cleaner {VERSION} - generated, do not edit.\n\n'
        "Regenerate with `python3 install.py --upgrade`.\n"
        'Source of truth: plugins/commit-cleaner/patterns.py\n"""\n'
        "import os\n"
        "import re\n"
        "import subprocess\n"
        "import sys\n"
    )
    parts = [header]
    for mod in ("patterns.py", "clean.py", "gitconfig.py"):
        parts.append(f"\n\n# ---- {mod} {'-' * (60 - len(mod))}\n")
        parts.append(_module_body(mod))
    parts.append(_MAIN)
    return "\n".join(parts)


def registry_path():
    # type: () -> Path
    """${CLAUDE_PLUGIN_DATA} is the documented persistent data directory that
    survives plugin updates. It is unset when install.py runs directly."""
    base = os.environ.get("CLAUDE_PLUGIN_DATA")
    if base:
        return Path(base) / "registry.json"
    return Path.home() / ".commit-cleaner" / "registry.json"


def _git(args, repo):
    # type: (list, str) -> subprocess.CompletedProcess
    try:
        return subprocess.run(
            ["git"] + args, cwd=repo, capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError:
        # Safety net: install_repo checks shutil.which("git") first and reports
        # this clearly, but nothing else that reaches _git may raise a
        # traceback if PATH changes underneath it mid-run.
        return subprocess.CompletedProcess(args, 127, stdout="", stderr="git: not found")


def resolve_hooks_dir(repo):
    # type: (str) -> Path
    """core.hooksPath wins over .git/hooks. Checking .git/hooks directly is
    wrong in any repo running husky, lefthook, or pre-commit."""
    custom = _git(["config", "--get", "core.hooksPath"], repo).stdout.strip()
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else Path(repo) / p
    got = _git(["rev-parse", "--git-path", "hooks"], repo).stdout.strip()
    return Path(repo) / got if got else Path(repo) / ".git" / "hooks"


def is_tracked(repo, path):
    # type: (str, Path) -> bool
    r = _git(["ls-files", "--error-unmatch", str(path)], repo)
    return r.returncode == 0


def _record(repo):
    # type: (str) -> None
    try:
        reg = registry_path()
        reg.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(reg.read_text()) if reg.exists() else {}
        data[str(repo)] = VERSION
        reg.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def install_repo(repo):
    # type: (str) -> Tuple[bool, str]
    """Returns (installed, message). Refuses a tracked hooks directory.

    Never writes anything unless git is present and repo is an actual git
    repository — "never write where you were not invited." Write failures
    (missing git, unwritable hooks dir) are reported, not raised: this is a
    CLI, so it may fail, it just may not crash with a traceback.
    """
    if shutil.which("git") is None:
        return False, "git was not found on PATH. Install git and retry."

    check = _git(["rev-parse", "--is-inside-work-tree"], repo)
    if check.returncode != 0 or check.stdout.strip() != "true":
        return False, f"{repo} is not a git repository."

    hooks = resolve_hooks_dir(repo)
    payload = generate_payload()

    try:
        tracked_dir = hooks.exists() and any(
            is_tracked(repo, p) for p in hooks.iterdir() if p.is_file()
        )
        if tracked_dir:
            side = Path(repo) / ".git" / "commit-cleaner.py"
            side.parent.mkdir(parents=True, exist_ok=True)
            side.write_text(payload)
            _record(repo)
            return False, (
                f"{hooks} is tracked by git, so installing there would dirty your "
                "working tree and be reverted by the next checkout. The payload is "
                f"at {side} instead. Add these two lines to your committed "
                "commit-msg hook:\n"
                '  command -v python3 >/dev/null 2>&1 && python3 "$(git rev-parse '
                '--git-dir)/commit-cleaner.py" "$1" || true\n'
            )

        hooks.mkdir(parents=True, exist_ok=True)
        existing = hooks / "commit-msg"
        chained = hooks / "commit-msg.chained"
        if existing.exists() and "commit-cleaner" not in existing.read_text():
            existing.replace(chained)
            chained.chmod(0o755)
        (hooks / "commit-cleaner.py").write_text(payload)
        existing.write_text(WRAPPER)
        existing.chmod(0o755)
        _record(repo)
        return True, f"installed into {hooks}"
    except OSError as exc:
        return False, f"could not write to {hooks}: {exc}. Check permissions and retry."


def uninstall_repo(repo):
    # type: (str) -> Tuple[bool, str]
    hooks = resolve_hooks_dir(repo)
    hook = hooks / "commit-msg"
    chained = hooks / "commit-msg.chained"
    if hook.exists() and "commit-cleaner" in hook.read_text():
        hook.unlink()
    if chained.exists():
        chained.replace(hook)
        hook.chmod(0o755)
    payload = hooks / "commit-cleaner.py"
    if payload.exists():
        payload.unlink()
    return True, f"uninstalled from {hooks}"


def _submodules(repo):
    # type: (str) -> list
    r = _git(["submodule", "foreach", "--quiet", "echo $sm_path"], repo)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def main(argv):
    # type: (list) -> int
    repo = os.getcwd()
    mode = argv[1] if len(argv) > 1 else "--install"

    if mode == "--list":
        reg = registry_path()
        print(reg.read_text() if reg.exists() else "{}")
        return 0
    if mode == "--uninstall":
        ok, msg = uninstall_repo(repo)
        print(msg)
        return 0 if ok else 1

    targets = [repo] + [os.path.join(repo, s) for s in _submodules(repo)]
    all_ok = True
    for t in targets:
        ok, msg = install_repo(t)
        print(("OK  " if ok else "SKIP ") + msg)
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
