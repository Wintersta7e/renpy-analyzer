"""Tests for checks/texttags.py — text tag validation in dialogue."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.texttags import check
from renpy_analyzer.models import (
    DialogueLine,
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
