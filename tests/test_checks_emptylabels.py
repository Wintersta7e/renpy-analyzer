"""Tests for empty label body check."""

import textwrap

from renpy_analyzer.checks.emptylabels import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_label_with_content(tmp_path):
    """Label with real content — no finding."""
    model = _project(tmp_path, """\
        label start:
            "Hello world"
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_empty_label(tmp_path):
    """Empty label followed by another label — HIGH finding."""
    model = _project(tmp_path, """\
        label empty_one:
        label real:
            "Hello"
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "HIGH"
    assert "empty_one" in findings[0].title
    assert findings[0].check_name == "emptylabels"


def test_label_with_only_pass(tmp_path):
    """Label with only pass — HIGH finding."""
    model = _project(tmp_path, """\
        label stub:
            pass
        label real:
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert "stub" in findings[0].title


def test_label_with_only_comments(tmp_path):
    """Label with only comments — HIGH finding (comments aren't content)."""
    model = _project(tmp_path, """\
        label todo:
            # TODO: implement this
            # more comments
        label real:
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert "todo" in findings[0].title


def test_label_at_end_of_file_empty(tmp_path):
    """Empty label at end of file — HIGH finding."""
    model = _project(tmp_path, """\
        label start:
            "content"
            return
        label trailing:
    """)
    findings = check(model)
    assert len(findings) == 1
    assert "trailing" in findings[0].title


def test_label_with_single_return(tmp_path):
    """Label with only a return statement — has content, no finding."""
    model = _project(tmp_path, """\
        label callback:
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_empty_model(tmp_path):
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []
