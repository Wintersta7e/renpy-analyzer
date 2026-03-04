"""Tests for narrator dialogue parsing and in_init flag."""

import textwrap

from renpy_analyzer.parser import parse_file


def _parse(tmp_path, content):
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return parse_file(str(f))


def test_narrator_dialogue_parsed(tmp_path):
    """Bare 'text' lines should be parsed as narrator dialogue."""
    result = _parse(
        tmp_path,
        """\
        label start:
            "This is narrator text."
    """,
    )
    narrators = [d for d in result["dialogue"] if d.speaker == ""]
    assert len(narrators) == 1
    assert narrators[0].text == "This is narrator text."


def test_narrator_with_text_tags(tmp_path):
    """Narrator lines with text tags should capture the text content."""
    result = _parse(
        tmp_path,
        """\
        label start:
            "This has {b}bold{/b} text."
    """,
    )
    narrators = [d for d in result["dialogue"] if d.speaker == ""]
    assert len(narrators) == 1
    assert "{b}" in narrators[0].text


def test_narrator_not_confused_with_speaker(tmp_path):
    """Speaker dialogue should still work alongside narrator lines."""
    result = _parse(
        tmp_path,
        """\
        label start:
            "Narrator text."
            mc "Speaker text."
    """,
    )
    narrators = [d for d in result["dialogue"] if d.speaker == ""]
    speakers = [d for d in result["dialogue"] if d.speaker == "mc"]
    assert len(narrators) == 1
    assert len(speakers) == 1


def test_narrator_not_matched_at_column_zero(tmp_path):
    """Bare strings at column 0 (like string definitions) should NOT match."""
    result = _parse(
        tmp_path,
        """\
"This is not narrator text"
label start:
    "This is narrator text."
    """,
    )
    narrators = [d for d in result["dialogue"] if d.speaker == ""]
    assert len(narrators) == 1


def test_narrator_fallback_unclosed_quote(tmp_path):
    """Narrator with unclosed quote should still be captured via fallback."""
    result = _parse(
        tmp_path,
        """\
        label start:
            "Unclosed narrator text
    """,
    )
    narrators = [d for d in result["dialogue"] if d.speaker == ""]
    assert len(narrators) == 1


def test_in_init_flag_set_in_init_block(tmp_path):
    """Variables inside init: blocks should have in_init=True."""
    result = _parse(
        tmp_path,
        """\
init:
    default config.rollback_enabled = False

label start:
    $ config.mouse_displayable = None
    """,
    )
    init_vars = [v for v in result["variables"] if v.in_init]
    runtime_vars = [v for v in result["variables"] if not v.in_init]
    assert len(init_vars) >= 1
    assert any(v.name == "config.rollback_enabled" for v in init_vars)
    assert any(v.name == "config.mouse_displayable" for v in runtime_vars)


def test_in_init_flag_for_default_define(tmp_path):
    """default/define at top level should NOT be marked as in_init."""
    result = _parse(
        tmp_path,
        """\
default myvar = False
define myconst = 42

init python:
    config.foo = "bar"
    """,
    )
    myvar = [v for v in result["variables"] if v.name == "myvar"]
    myconst = [v for v in result["variables"] if v.name == "myconst"]
    assert len(myvar) == 1
    assert not myvar[0].in_init
    assert len(myconst) == 1
    assert not myconst[0].in_init


def test_in_init_exits_on_dedent(tmp_path):
    """Init context should end when indentation returns to column 0."""
    result = _parse(
        tmp_path,
        """\
init:
    default inside_init = True

default outside_init = False
    """,
    )
    inside = [v for v in result["variables"] if v.name == "inside_init"]
    outside = [v for v in result["variables"] if v.name == "outside_init"]
    assert len(inside) == 1
    assert inside[0].in_init
    assert len(outside) == 1
    assert not outside[0].in_init
