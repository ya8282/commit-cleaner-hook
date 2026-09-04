"""The stripping function. Pure: no I/O, no config, no git."""
import re  # noqa: F401


def clean(text, patterns):
    # type: (str, list[re.Pattern[str]]) -> str
    """Delete every line matching any pattern, then collapse the trailing blank
    lines the deletions leave behind.

    Returns the ORIGINAL text unchanged if stripping would empty it: git aborts
    a commit whose message is empty, and this tool never blocks a commit.
    """
    if not text:
        return text

    kept = [ln for ln in text.splitlines() if not any(p.search(ln) for p in patterns)]
    while kept and not kept[-1].strip():
        kept.pop()

    if not kept:
        return text

    result = "\n".join(kept) + "\n"
    return text if not result.strip() else result
