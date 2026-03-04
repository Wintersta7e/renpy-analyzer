"""Tests for jump-in-call stack leak detection."""

import textwrap

from renpy_analyzer.checks.callreturn import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_call_to_label_that_jumps(tmp_path):
    """Called label ending with jump (no return) should be HIGH."""
    model = _project(
        tmp_path,
        """\
        label start:
            call helper

        label helper:
            "Doing stuff"
            jump elsewhere

        label elsewhere:
            "End"
    """,
    )
    findings = check(model)
    jump_findings = [f for f in findings if "jumps instead" in f.title]
    assert len(jump_findings) == 1
    assert jump_findings[0].severity.name == "HIGH"
    assert "helper" in jump_findings[0].title


def test_call_to_label_with_return(tmp_path):
    """Called label with return should not be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            call helper

        label helper:
            "Doing stuff"
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_call_to_label_no_return_no_jump(tmp_path):
    """Called label with neither return nor jump should be CRITICAL (existing check)."""
    model = _project(
        tmp_path,
        """\
        label start:
            call helper

        label helper:
            "Doing stuff"
    """,
    )
    findings = check(model)
    critical = [f for f in findings if "never returns" in f.title]
    assert len(critical) == 1
    assert critical[0].severity.name == "CRITICAL"
