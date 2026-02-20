"""Tests for flow/unreachable code check."""

import textwrap

from renpy_analyzer.checks.flow import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_unreachable_after_jump(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
            jump ending
            "This is unreachable"
        label ending:
            return
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 1
    assert unreach[0].severity.name == "HIGH"


def test_unreachable_after_return(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
            return
            "Never seen"
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 1


def test_no_false_positive_on_label_boundary(tmp_path):
    """Code in a new label after jump in previous label is NOT unreachable."""
    model = _project(
        tmp_path,
        """\
        label start:
            jump ending
        label ending:
            "This is reachable"
            return
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 0


def test_no_false_positive_on_menu(tmp_path):
    """Code inside menu choices after jump elsewhere is fine."""
    model = _project(
        tmp_path,
        """\
        label start:
            menu:
                "Go left":
                    jump left_path
                "Go right":
                    jump right_path
        label left_path:
            return
        label right_path:
            return
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 0


def test_empty_model_returns_empty(tmp_path):
    """Flow check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel

    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_comment_between_jump_and_unreachable(tmp_path):
    """Comments between jump and unreachable code should not prevent detection."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
            jump ending
            # This is a comment
            "Unreachable line"
        label ending:
            return
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 1


def test_unreachable_after_return_expression(tmp_path):
    """'return True' and 'return expr' should also trigger unreachable detection."""
    model = _project(
        tmp_path,
        """\
        label helper:
            "Doing work"
            return True
            "This is unreachable"
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 1


def test_return_value_detected(tmp_path):
    """return with a value (return _return) should be detected as a terminator."""
    model = _project(
        tmp_path,
        """\
        label compute:
            $ result = 42
            return result
            $ result = 0
    """,
    )
    findings = check(model)
    unreach = [f for f in findings if "Unreachable" in f.title]
    assert len(unreach) == 1
