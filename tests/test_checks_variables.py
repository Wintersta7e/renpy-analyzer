"""Tests for variables check."""
import textwrap
from renpy_analyzer.project import load_project
from renpy_analyzer.checks.variables import check


def _project(tmp_path, vars_content, script_content=""):
    game = tmp_path / "game"
    game.mkdir()
    (game / "variables.rpy").write_text(textwrap.dedent(vars_content), encoding="utf-8")
    if script_content:
        (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_case_mismatch(tmp_path):
    model = _project(tmp_path, """\
        default myFlag = False
        default MyFlag = False
    """)
    findings = check(model)
    case_findings = [f for f in findings if "case mismatch" in f.title.lower()]
    assert len(case_findings) >= 2


def test_undeclared_variable(tmp_path):
    model = _project(tmp_path, "", """\
        label start:
            $ Temp1 = 0
    """)
    findings = check(model)
    undecl = [f for f in findings if "Undeclared" in f.title]
    assert len(undecl) == 1
    assert "Temp1" in undecl[0].title


def test_unused_variable(tmp_path):
    model = _project(tmp_path, """\
        default NeverUsed = False
    """)
    findings = check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert len(unused) == 1
    assert "NeverUsed" in unused[0].title


def test_used_variable_not_flagged_unused(tmp_path):
    model = _project(tmp_path, """\
        default Lydia = 0
    """, """\
        label start:
            $ Lydia += 1
    """)
    findings = check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert len(unused) == 0


def test_pattern_case_mismatch(tmp_path):
    """Detect case mismatch in numbered variable families."""
    model = _project(tmp_path, """\
        default marysex4_slow_1 = False
        default marysex4_slow_2 = False
        default marysex4_Slow_3 = False
    """)
    findings = check(model)
    case_findings = [f for f in findings if "case mismatch" in f.title.lower()]
    assert len(case_findings) >= 1
    assert any("marysex4_Slow_3" in f.title for f in case_findings)
