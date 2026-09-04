#!/usr/bin/env python3
"""Generates and installs the self-contained commit-msg payload.

The installed copy must run with no plugin present, and ${CLAUDE_PLUGIN_ROOT}
is versioned and garbage-collected, so a hook pointing into it would become a
dangling path — which blocks commits. Hence: inline, copy, stamp a version.
"""
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
