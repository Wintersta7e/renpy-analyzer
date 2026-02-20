"""Tests for labels check."""

import textwrap

from renpy_analyzer.checks.labels import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_missing_label_detected(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"
    assert "nonexistent" in findings[0].title


def test_valid_jumps_no_findings(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            jump ending
        label ending:
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_duplicate_label_detected(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            jump ending
        label ending:
            return
        label ending:
            return
    """,
    )
    findings = check(model)
    dupes = [f for f in findings if "Duplicate" in f.title]
    assert len(dupes) == 2


def test_jump_expression_flagged(tmp_path):
    """jump expression should produce an informational finding."""
    model = _project(
        tmp_path,
        """\
        label start:
            jump expression target_var
    """,
    )
    findings = check(model)
    expr = [f for f in findings if "expression" in f.title.lower() or "dynamic" in f.title.lower()]
    assert len(expr) == 1
    assert expr[0].severity.name == "MEDIUM"


def test_empty_model_returns_empty(tmp_path):
    """Labels check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel

    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_missing_call_target(tmp_path):
    """call to nonexistent label should produce CRITICAL finding."""
    model = _project(
        tmp_path,
        """\
        label start:
            call nonexistent
    """,
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"
    assert "nonexistent" in findings[0].title


def test_cross_file_jump_valid(tmp_path):
    """A jump to a label defined in another file should not produce a finding."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "file1.rpy").write_text("label start:\n    jump helper\n", encoding="utf-8")
    (game / "file2.rpy").write_text("label helper:\n    return\n", encoding="utf-8")
    model = load_project(str(tmp_path))
    findings = check(model)
    assert len(findings) == 0
