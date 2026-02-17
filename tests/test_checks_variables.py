"""Tests for variables check."""
import textwrap

from renpy_analyzer.checks.variables import check
from renpy_analyzer.project import load_project


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


def test_define_then_assign_flagged(tmp_path):
    """define variable later modified via $ should be flagged."""
    model = _project(tmp_path, """\
        define points = 0
    """, """\
        label start:
            $ points += 1
    """)
    findings = check(model)
    mutated = [f for f in findings if "define" in f.title.lower() and "mutated" in f.title.lower()]
    assert len(mutated) == 1
    assert "points" in mutated[0].title
    assert mutated[0].severity.name == "CRITICAL"


def test_define_not_modified_no_flag(tmp_path):
    """define variable never modified should not be flagged."""
    model = _project(tmp_path, """\
        define e = Character("Eileen")
    """, """\
        label start:
            e "Hello!"
    """)
    findings = check(model)
    mutated = [f for f in findings if "mutated" in f.title.lower()]
    assert len(mutated) == 0


def test_duplicate_default_detected(tmp_path):
    """Same variable declared with default in two files."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "vars1.rpy").write_text("default points = 0\n", encoding="utf-8")
    (game / "vars2.rpy").write_text("default points = 10\n", encoding="utf-8")
    model = load_project(str(tmp_path))
    findings = check(model)
    dupes = [f for f in findings if "Duplicate" in f.title and "points" in f.title]
    assert len(dupes) >= 1
    assert dupes[0].severity.name == "HIGH"


def test_define_persistent_flagged(tmp_path):
    """define persistent.X should use default instead."""
    model = _project(tmp_path, """\
        define persistent.ending_seen = False
    """)
    findings = check(model)
    persist = [f for f in findings if "persistent" in f.title.lower()]
    assert len(persist) == 1
    assert persist[0].severity.name == "HIGH"


def test_builtin_shadowing_detected(tmp_path):
    """define/default using a Python builtin name should be flagged."""
    model = _project(tmp_path, """\
        default list = []
        default str = "hello"
    """)
    findings = check(model)
    shadow = [f for f in findings if "shadow" in f.title.lower() or "builtin" in f.title.lower()]
    assert len(shadow) == 2
    assert shadow[0].severity.name == "HIGH"
