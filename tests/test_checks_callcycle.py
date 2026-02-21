"""Tests for circular call cycle check."""

import textwrap

from renpy_analyzer.checks.callcycle import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_no_cycles(tmp_path):
    """Simple call chain with no cycles — no findings."""
    model = _project(tmp_path, """\
        label start:
            call helper
            return
        label helper:
            "work"
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_self_recursion(tmp_path):
    """Label calls itself — CRITICAL finding."""
    model = _project(tmp_path, """\
        label recursive:
            call recursive
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"
    assert "recursive" in findings[0].title
    assert findings[0].check_name == "callcycle"


def test_two_node_cycle(tmp_path):
    """A calls B, B calls A — CRITICAL finding."""
    model = _project(tmp_path, """\
        label alpha:
            call beta
            return
        label beta:
            call alpha
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"


def test_three_node_cycle(tmp_path):
    """A → B → C → A cycle."""
    model = _project(tmp_path, """\
        label a:
            call b
            return
        label b:
            call c
            return
        label c:
            call a
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"


def test_chain_no_cycle(tmp_path):
    """A → B → C chain (no cycle) — no findings."""
    model = _project(tmp_path, """\
        label a:
            call b
            return
        label b:
            call c
            return
        label c:
            "end"
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_two_independent_cycles(tmp_path):
    """Two separate cycles — two findings."""
    model = _project(tmp_path, """\
        label a:
            call b
            return
        label b:
            call a
            return
        label x:
            call y
            return
        label y:
            call x
            return
    """)
    findings = check(model)
    assert len(findings) == 2


def test_call_to_undefined_label(tmp_path):
    """Call to undefined label — no finding (handled by labels check)."""
    model = _project(tmp_path, """\
        label start:
            call nonexistent
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_empty_model(tmp_path):
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []
