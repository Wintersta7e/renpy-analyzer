"""Tests for checks/texttags.py — text tag validation in dialogue."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.texttags import _extract_brackets, _strip_renpy_suffixes, check
from renpy_analyzer.models import (
    DialogueLine,
    Menu,
    MenuChoice,
    ProjectModel,
    Severity,
)
from renpy_analyzer.parser import parse_file


def _model(**kwargs) -> ProjectModel:
    return ProjectModel(root_dir="/test", **kwargs)


# --- Check logic tests ---


def test_unclosed_tag():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello {b}world")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert "Unclosed" in findings[0].description


def test_properly_closed():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello {b}world{/b}")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_unknown_tag():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello {xyz}world")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    assert "Unknown" in findings[0].description


def test_mismatched_nesting():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="{b}{i}text{/b}{/i}")],
    )
    findings = check(model)
    assert len(findings) >= 1
    assert any("Mismatched" in f.description for f in findings)


def test_self_closing_ok():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello{w} world{nw}")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_closing_without_opening():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello {/b}world")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert "without opening" in findings[0].description


def test_multiple_errors():
    model = _model(
        dialogue=[
            DialogueLine(speaker="mc", file="s.rpy", line=5, text="{b}bold"),
            DialogueLine(speaker="mc", file="s.rpy", line=6, text="{xyz}unknown"),
        ],
    )
    findings = check(model)
    assert len(findings) == 2


def test_empty_text_graceful():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_no_text_field():
    """Dialogue without text (default empty) should not cause errors."""
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5)],
    )
    findings = check(model)
    assert len(findings) == 0


def test_valid_tags_with_values():
    model = _model(
        dialogue=[
            DialogueLine(
                speaker="mc",
                file="s.rpy",
                line=5,
                text="{color=#ff0000}Red text{/color} {size=+5}big{/size}",
            )
        ],
    )
    findings = check(model)
    assert len(findings) == 0


def test_hash_tag():
    """The {#} tag for accessibility comments should be recognized."""
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello{#this is a comment}")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_empty_model():
    model = _model()
    findings = check(model)
    assert findings == []


# --- Parser extraction tests ---


def _write_rpy(tmp_path: Path, content: str) -> str:
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


def test_parser_text_capture(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            mc "Hello {b}world{/b}"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 1
    assert result["dialogue"][0].text == "Hello {b}world{/b}"


def test_parser_escaped_quotes(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            mc "She said \\"hello\\""
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 1
    assert "hello" in result["dialogue"][0].text


def test_parser_fallback_unclosed_quote(tmp_path):
    """Unclosed quote should still be captured (speaker only, no text)."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            mc "This quote is never closed
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 1
    assert result["dialogue"][0].speaker == "mc"
    assert result["dialogue"][0].text == ""


def test_parser_multiline_not_captured(tmp_path):
    """Multi-line strings are common in Ren'Py; fallback should capture speaker."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            mc "First line"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 1
    assert result["dialogue"][0].text == "First line"


# --- Bracket extraction unit tests ---


def test_extract_simple_var():
    assert _extract_brackets("Hello [name]!") == [("name", 6, True)]


def test_extract_nested_brackets():
    assert _extract_brackets("Val: [items[0]]") == [("items[0]", 5, True)]


def test_extract_escaped_skip():
    assert _extract_brackets("Price [[100] coins") == []


def test_extract_quoted_bracket():
    """Bracket inside quotes should not close the expression."""
    result = _extract_brackets('[player.name + " ]san"]')
    assert len(result) == 1
    assert result[0][0] == 'player.name + " ]san"'
    assert result[0][2] is True


def test_extract_unclosed():
    """Unclosed bracket yields partial content with closed=False."""
    result = _extract_brackets("Hello [name")
    assert len(result) == 1
    assert result[0][0] == "name"
    assert result[0][2] is False


def test_extract_multiple():
    result = _extract_brackets("[a] and [b]")
    assert result == [("a", 0, True), ("b", 8, True)]


def test_extract_empty_brackets():
    assert _extract_brackets("text [] here") == [("", 5, True)]


# --- Suffix stripping unit tests ---


def test_strip_no_suffix():
    assert _strip_renpy_suffixes("name") == "name"


def test_strip_format_spec():
    assert _strip_renpy_suffixes("score:.2f") == "score"


def test_strip_conversion_flag():
    assert _strip_renpy_suffixes("name!u") == "name"


def test_strip_multi_conversion():
    assert _strip_renpy_suffixes("name!cl") == "name"


def test_strip_conv_and_format():
    assert _strip_renpy_suffixes("score!u:.2f") == "score"


def test_strip_reverse_order():
    """Ren'Py accepts [expr:fmt!conv] too."""
    assert _strip_renpy_suffixes("score:.2f!u") == "score"


def test_strip_debug_equals():
    assert _strip_renpy_suffixes("my_var=") == "my_var"


def test_strip_debug_equals_with_conv():
    assert _strip_renpy_suffixes("var=!u") == "var"


def test_strip_ne_operator_preserved():
    """!= is an operator, not a conversion separator."""
    assert _strip_renpy_suffixes("x != 5") == "x != 5"


def test_strip_colon_in_parens():
    """Colon inside parens is not a format spec (e.g., dict-like)."""
    assert _strip_renpy_suffixes("(1, 'one')") == "(1, 'one')"


def test_strip_colon_in_slice():
    """Colon inside brackets is a slice, not format spec."""
    assert _strip_renpy_suffixes("items[1:3]") == "items[1:3]"


# --- Bracket validation integration tests ---


def test_bracket_valid_simple_var():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="Hello [name]!")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_attribute():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="HP: [player.hp]")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_conversion_flags():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="[name!u] and [x!cl]")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_format_spec():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="Score: [score:.2f]")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_combined_suffixes():
    """Both orders: [expr!conv:fmt] and [expr:fmt!conv]."""
    model = _model(
        dialogue=[
            DialogueLine(speaker="mc", file="s.rpy", line=1, text="[score!u:.2f]"),
            DialogueLine(speaker="mc", file="s.rpy", line=2, text="[score:.2f!u]"),
        ],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_ne_operator():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="[x != 5]")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_nested():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="[items[0]]")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_debug_equals():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="[my_var=]")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_valid_complex_expression():
    """Function call, ternary, and quoted strings inside brackets are valid."""
    model = _model(
        dialogue=[
            DialogueLine(speaker="mc", file="s.rpy", line=1, text='[len(items)]'),
            DialogueLine(speaker="mc", file="s.rpy", line=2, text='["yes" if flag else "no"]'),
            DialogueLine(speaker="mc", file="s.rpy", line=3, text='[player.name + " san"]'),
        ],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_escaped_no_finding():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=1, text="Price [[100] coins")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_bracket_unescaped_natural_language():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Status: [Sent photo]")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "Sent photo" in findings[0].description
    assert "[[" in findings[0].suggestion


def test_bracket_unescaped_multi_word():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="[Click here] to continue")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH


def test_bracket_empty():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Empty [] here")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH


def test_bracket_unclosed():
    model = _model(
        dialogue=[DialogueLine(speaker="mc", file="s.rpy", line=5, text="Hello [name")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].title == "Unclosed square bracket"
    assert "missing closing" in findings[0].description


def test_bracket_menu_choice():
    model = _model(
        menus=[
            Menu(
                file="s.rpy",
                line=10,
                choices=[
                    MenuChoice(
                        text="Go to [the park]",
                        line=11,
                        content_lines=1,
                        has_jump=False,
                        has_return=False,
                    ),
                ],
            ),
        ],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "the park" in findings[0].description
