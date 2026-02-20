"""Tests for checks/screens.py — screen definition/reference validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.screens import check
from renpy_analyzer.models import (
    ProjectModel,
    ScreenDef,
    ScreenRef,
    Severity,
)
from renpy_analyzer.parser import parse_file


def _model(**kwargs) -> ProjectModel:
    return ProjectModel(root_dir="/test", **kwargs)


# --- Check logic tests ---


def test_undefined_show_screen():
    model = _model(
        screen_refs=[ScreenRef(name="inventory", file="s.rpy", line=5, action="show")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "inventory" in findings[0].title


def test_undefined_call_screen():
    model = _model(
        screen_refs=[ScreenRef(name="settings", file="s.rpy", line=10, action="call")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "settings" in findings[0].title


def test_undefined_hide_screen():
    model = _model(
        screen_refs=[ScreenRef(name="overlay", file="s.rpy", line=3, action="hide")],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH


def test_duplicate_screen():
    model = _model(
        screen_defs=[
            ScreenDef(name="inventory", file="a.rpy", line=1),
            ScreenDef(name="inventory", file="b.rpy", line=5),
        ],
    )
    findings = check(model)
    dups = [f for f in findings if f.severity == Severity.MEDIUM]
    assert len(dups) == 1
    assert "Duplicate" in dups[0].title


def test_unused_screen():
    model = _model(
        screen_defs=[ScreenDef(name="inventory", file="s.rpy", line=1)],
    )
    findings = check(model)
    unused = [f for f in findings if f.severity == Severity.LOW]
    assert len(unused) == 1
    assert "Unused" in unused[0].title


def test_builtin_screen_no_warning():
    model = _model(
        screen_refs=[ScreenRef(name="say", file="s.rpy", line=5, action="show")],
    )
    findings = check(model)
    assert len(findings) == 0


def test_builtin_screen_unused_no_warning():
    """Builtin screen names should not be reported as unused even if defined."""
    model = _model(
        screen_defs=[ScreenDef(name="say", file="s.rpy", line=1)],
    )
    findings = check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert len(unused) == 0


def test_clean_case():
    model = _model(
        screen_defs=[ScreenDef(name="inventory", file="s.rpy", line=1)],
        screen_refs=[ScreenRef(name="inventory", file="s.rpy", line=10, action="show")],
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


def test_parser_screen_def(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        screen inventory():
            vbox:
                text "Items"
    """,
    )
    result = parse_file(path)
    assert len(result["screen_defs"]) == 1
    assert result["screen_defs"][0].name == "inventory"


def test_parser_screen_refs(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            show screen inventory
            call screen settings
            hide screen overlay
    """,
    )
    result = parse_file(path)
    assert len(result["screen_refs"]) == 3
    names = [(r.name, r.action) for r in result["screen_refs"]]
    assert ("inventory", "show") in names
    assert ("settings", "call") in names
    assert ("overlay", "hide") in names


def test_parser_show_screen_not_image(tmp_path):
    """'show screen X' should NOT be parsed as image show."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            show screen inventory
            show eileen happy
    """,
    )
    result = parse_file(path)
    assert len(result["screen_refs"]) == 1
    assert result["screen_refs"][0].name == "inventory"
    assert len(result["shows"]) == 1
    assert result["shows"][0].image_name == "eileen happy"


def test_parser_call_screen_not_label(tmp_path):
    """'call screen X' should NOT be parsed as label call."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            call screen settings
            call helper
    """,
    )
    result = parse_file(path)
    assert len(result["screen_refs"]) == 1
    assert result["screen_refs"][0].name == "settings"
    assert len(result["calls"]) == 1
    assert result["calls"][0].target == "helper"
