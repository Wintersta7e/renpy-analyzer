"""Tests for menus check."""
import textwrap

from renpy_analyzer.checks.menus import check
from renpy_analyzer.models import Severity
from renpy_analyzer.project import load_project


def _project(tmp_path, script):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    return load_project(str(tmp_path))


def test_empty_choice(tmp_path):
    model = _project(tmp_path, """\
        label start:
            menu:
                "Choice A":
                    mc "Picked A"
                    mc "More A"
                    mc "Even more A"
                "Choice B":

        label next:
            return
    """)
    findings = check(model)
    empty = [f for f in findings if f.severity == Severity.HIGH]
    assert len(empty) == 1
    assert "Empty" in empty[0].title


def test_fallthrough(tmp_path):
    model = _project(tmp_path, """\
        label start:
            menu:
                "Short":
                    mc "Just one line"
                "Long":
                    mc "Line 1"
                    mc "Line 2"
                    mc "Line 3"
                    mc "Line 4"
        label next:
            return
    """)
    findings = check(model)
    ft = [f for f in findings if "fallthrough" in f.title.lower()]
    assert len(ft) == 1


def test_single_choice(tmp_path):
    model = _project(tmp_path, """\
        label start:
            menu:
                "Only option":
                    jump next
        label next:
            return
    """)
    findings = check(model)
    single = [f for f in findings if "Single" in f.title]
    assert len(single) == 1


def test_empty_model_returns_empty(tmp_path):
    """Menus check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_choice_with_return_no_fallthrough(tmp_path):
    """A choice with 'return' should not be flagged as fallthrough."""
    model = _project(tmp_path, """\
        label start:
            menu:
                "Short":
                    return
                "Long":
                    mc "Line 1"
                    mc "Line 2"
                    mc "Line 3"
                    mc "Line 4"
        label next:
            return
    """)
    findings = check(model)
    ft = [f for f in findings if "fallthrough" in f.title.lower()]
    assert len(ft) == 0


def test_all_choices_with_jumps_no_fallthrough(tmp_path):
    """All choices having jumps means no fallthroughs."""
    model = _project(tmp_path, """\
        label start:
            menu:
                "Go A":
                    jump a
                "Go B":
                    mc "Line 1"
                    mc "Line 2"
                    mc "Line 3"
                    jump b
        label a:
            return
        label b:
            return
    """)
    findings = check(model)
    ft = [f for f in findings if "fallthrough" in f.title.lower()]
    assert len(ft) == 0
