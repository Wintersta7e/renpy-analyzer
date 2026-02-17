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
    model = _project(tmp_path, """\
        label start:
            jump nonexistent
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "CRITICAL"
    assert "nonexistent" in findings[0].title


def test_valid_jumps_no_findings(tmp_path):
    model = _project(tmp_path, """\
        label start:
            jump ending
        label ending:
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_duplicate_label_detected(tmp_path):
    model = _project(tmp_path, """\
        label start:
            jump ending
        label ending:
            return
        label ending:
            return
    """)
    findings = check(model)
    dupes = [f for f in findings if "Duplicate" in f.title]
    assert len(dupes) == 2


def test_jump_expression_flagged(tmp_path):
    """jump expression should produce an informational finding."""
    model = _project(tmp_path, """\
        label start:
            jump expression target_var
    """)
    findings = check(model)
    expr = [f for f in findings if "expression" in f.title.lower() or "dynamic" in f.title.lower()]
    assert len(expr) == 1
    assert expr[0].severity.name == "MEDIUM"
