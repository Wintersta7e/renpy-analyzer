"""Tests for call-without-return check."""

import textwrap

from renpy_analyzer.checks.callreturn import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_call_to_label_with_return(tmp_path):
    """Call to a label that returns — no finding."""
    model = _project(tmp_path, """\
        label start:
            call helper
            return
        label helper:
            "Doing work"
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_call_to_label_without_return(tmp_path):
    """Call to a label that ends with jump — CRITICAL finding."""
    model = _project(tmp_path, """\
        label start:
            call helper
            return
        label helper:
            "Doing work"
            jump ending
        label ending:
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"
    assert "helper" in findings[0].title
    assert findings[0].check_name == "callreturn"


def test_call_to_missing_label(tmp_path):
    """Call to undefined label — no finding (handled by labels check)."""
    model = _project(tmp_path, """\
        label start:
            call nonexistent
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_call_to_label_with_conditional_return(tmp_path):
    """Label has return in one branch — no finding (has_return=True)."""
    model = _project(tmp_path, """\
        label start:
            call helper
            return
        label helper:
            if condition:
                return
            jump fallback
        label fallback:
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_call_to_label_with_only_pass(tmp_path):
    """Label with only pass — CRITICAL finding (no return)."""
    model = _project(tmp_path, """\
        label start:
            call stub
            return
        label stub:
            pass
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"


def test_multiple_calls_to_same_bad_label(tmp_path):
    """Multiple calls to same non-returning label — one finding per call site."""
    model = _project(tmp_path, """\
        label start:
            call bad_label
            call bad_label
            return
        label bad_label:
            jump somewhere
        label somewhere:
            return
    """)
    findings = check(model)
    assert len(findings) == 2


def test_return_after_unreachable_jump(tmp_path):
    """Label has return after jump — has_return still True, no finding."""
    model = _project(tmp_path, """\
        label start:
            call helper
            return
        label helper:
            jump somewhere
            return
        label somewhere:
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_call_screen_not_flagged(tmp_path):
    """'call screen X' is a screen call, not a label call — no finding."""
    model = _project(tmp_path, """\
        label start:
            call screen preferences
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_empty_model(tmp_path):
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []
