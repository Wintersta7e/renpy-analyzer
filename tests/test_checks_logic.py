"""Tests for logic check."""

import textwrap

from renpy_analyzer.checks.logic import check
from renpy_analyzer.models import Severity
from renpy_analyzer.project import load_project


def _project(tmp_path, script):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    return load_project(str(tmp_path))


def test_precedence_bug_or_equals_true(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            if SamSex2 or SamSex3 == True:
                jump a
    """,
    )
    findings = check(model)
    critical = [f for f in findings if f.severity == Severity.CRITICAL]
    assert len(critical) == 1
    assert "precedence" in critical[0].title.lower()


def test_precedence_bug_and_equals_false(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            if VarA and VarB == False:
                jump a
    """,
    )
    findings = check(model)
    critical = [f for f in findings if f.severity == Severity.CRITICAL]
    assert len(critical) == 1


def test_correct_form_not_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            if LydiaMary3Some1 == True or MarySolo == True:
                jump a
    """,
    )
    findings = check(model)
    critical = [f for f in findings if f.severity == Severity.CRITICAL]
    assert len(critical) == 0


def test_explicit_bool_style(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            if MyFlag == True:
                jump a
    """,
    )
    findings = check(model)
    style = [f for f in findings if f.severity == Severity.STYLE]
    assert len(style) == 1


def test_empty_model_returns_empty(tmp_path):
    """Logic check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel

    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_explicit_bool_false_style(tmp_path):
    """== False should also produce a STYLE finding."""
    model = _project(
        tmp_path,
        """\
        label start:
            if MyFlag == False:
                jump a
    """,
    )
    findings = check(model)
    style = [f for f in findings if f.severity == Severity.STYLE]
    assert len(style) == 1
    assert "False" in style[0].title


def test_elif_precedence_bug(tmp_path):
    """Precedence bug in elif should be caught too."""
    model = _project(
        tmp_path,
        """\
        label start:
            if True:
                jump a
            elif VarX or VarY == True:
                jump b
    """,
    )
    findings = check(model)
    critical = [f for f in findings if f.severity == Severity.CRITICAL]
    assert len(critical) == 1
