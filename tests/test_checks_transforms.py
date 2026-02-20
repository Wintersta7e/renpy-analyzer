"""Tests for checks/transforms.py — transform definition/reference validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.transforms import check
from renpy_analyzer.models import (
    ProjectModel,
    Severity,
    TransformDef,
    TransformRef,
)
from renpy_analyzer.parser import parse_file


def _model(**kwargs) -> ProjectModel:
    return ProjectModel(root_dir="/test", **kwargs)


# --- Check logic tests ---


def test_undefined_transform():
    model = _model(
        transform_refs=[TransformRef(name="custom_slide", file="s.rpy", line=5)],
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert "custom_slide" in findings[0].title


def test_builtin_transform_no_warning():
    model = _model(
        transform_refs=[TransformRef(name="left", file="s.rpy", line=5)],
    )
    findings = check(model)
    assert len(findings) == 0


def test_duplicate_transform():
    model = _model(
        transform_defs=[
            TransformDef(name="slide_in", file="a.rpy", line=1),
            TransformDef(name="slide_in", file="b.rpy", line=5),
        ],
    )
    findings = check(model)
    dups = [f for f in findings if f.severity == Severity.MEDIUM]
    assert len(dups) == 1
    assert "Duplicate" in dups[0].title


def test_unused_transform():
    model = _model(
        transform_defs=[TransformDef(name="slide_in", file="s.rpy", line=1)],
    )
    findings = check(model)
    unused = [f for f in findings if f.severity == Severity.LOW]
    assert len(unused) == 1
    assert "Unused" in unused[0].title


def test_clean_case():
    model = _model(
        transform_defs=[TransformDef(name="slide_in", file="s.rpy", line=1)],
        transform_refs=[TransformRef(name="slide_in", file="s.rpy", line=10)],
    )
    findings = check(model)
    assert len(findings) == 0


def test_empty_model():
    model = _model()
    findings = check(model)
    assert findings == []


def test_builtin_not_reported_unused():
    """Builtin transforms should not be reported as unused even if defined."""
    model = _model(
        transform_defs=[TransformDef(name="left", file="s.rpy", line=1)],
    )
    findings = check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert len(unused) == 0


# --- Parser extraction tests ---


def _write_rpy(tmp_path: Path, content: str) -> str:
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


def test_parser_transform_def(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        transform slide_in:
            xalign 0.0
            linear 1.0 xalign 1.0
    """,
    )
    result = parse_file(path)
    assert len(result["transform_defs"]) == 1
    assert result["transform_defs"][0].name == "slide_in"


def test_parser_at_transform_show(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            show eileen happy at right
    """,
    )
    result = parse_file(path)
    assert len(result["transform_refs"]) == 1
    assert result["transform_refs"][0].name == "right"


def test_parser_at_transform_scene(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            scene bg park at custom_pan
    """,
    )
    result = parse_file(path)
    assert len(result["transform_refs"]) == 1
    assert result["transform_refs"][0].name == "custom_pan"


def test_parser_show_without_at(tmp_path):
    """show without 'at' should not produce transform refs."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            show eileen happy
    """,
    )
    result = parse_file(path)
    assert len(result["transform_refs"]) == 0
