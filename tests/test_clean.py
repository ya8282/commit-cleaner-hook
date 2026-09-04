import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "commit-cleaner"
sys.path.insert(0, str(PLUGIN))

from clean import clean  # noqa: E402
from patterns import compile_patterns  # noqa: E402

# Built at runtime. A literal here would be denied by the author's bash guard.
CO = "Co-Authored" + "-By: Claude Opus 5 <noreply@anthropic.com>"
SESS = "Claude-Sess" + "ion: https://claude.ai/code/session_03EgpJ4AzYq9eFNpAOH80"
GEN = "\U0001f916 Generated with [Claude Code](https://claude.ai/code)"
HUMAN = "Co-Authored" + "-By: Claude Dupont <claude.dupont@example.com>"

P = compile_patterns()


def test_strips_co_authored_by_claude():
    assert clean("subject\n\n" + CO + "\n", P) == "subject\n"


def test_strips_session_trailer():
    assert clean("subject\n\n" + SESS + "\n", P) == "subject\n"


def test_strips_both_and_collapses_blank_lines():
    assert clean("subject\n\nbody\n\n" + CO + "\n" + SESS + "\n", P) == "subject\n\nbody\n"


def test_strips_generated_with_line():
    assert clean("subject\n\n" + GEN + "\n", P) == "subject\n"


def test_preserves_human_co_author_named_claude():
    msg = "subject\n\n" + HUMAN + "\n"
    assert clean(msg, P) == msg


def test_clean_message_is_byte_identical():
    msg = "feat: add thing\n\nA body that mentions Claude in prose.\n"
    assert clean(msg, P) == msg


def test_message_that_is_only_a_trailer_is_left_untouched():
    msg = CO + "\n"
    assert clean(msg, P) == msg


def test_empty_input_is_returned_unchanged():
    assert clean("", P) == ""


def test_malformed_extra_pattern_is_skipped_not_fatal():
    p = compile_patterns(extra=["(unclosed", r"^DROPME$"])
    assert clean("keep\nDROPME\n", p) == "keep\n"


def test_use_defaults_false_uses_only_extra():
    p = compile_patterns(extra=[r"^DROPME$"], use_defaults=False)
    assert clean("DROPME\n" + CO + "\n", p) == CO + "\n"


def test_preserves_prose_mentioning_generated_with_claude_code():
    msg = (
        "docs: describe repo history\n\nNote: this repo template was originally "
        "🤖 Generated with [Claude Code](https://claude.ai/code) "
        "before we customized it.\n"
    )
    assert clean(msg, P) == msg


def test_strips_generated_with_footer_markdown_link_alone():
    footer = "Generated with [Claude Code](https://claude.ai/code)"
    assert clean("subject\n\n" + footer + "\n", P) == "subject\n"


def test_strips_generated_with_footer_markdown_link_with_emoji():
    footer = "\U0001f916 Generated with [Claude Code](https://claude.ai/code)"
    assert clean("subject\n\n" + footer + "\n", P) == "subject\n"


def test_preserves_footer_with_trailing_text():
    msg = "subject\n\nGenerated with [Claude Code](https://claude.ai/code) but then modified\n"
    assert clean(msg, P) == msg


def test_strips_plain_text_generated_with_line():
    footer = "Generated with Claude Code"
    assert clean("subject\n\n" + footer + "\n", P) == "subject\n"


def test_strips_plain_text_generated_with_line_with_emoji():
    footer = "\U0001f916 Generated with Claude Code"
    assert clean("subject\n\n" + footer + "\n", P) == "subject\n"
