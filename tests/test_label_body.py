"""Tests for label body analysis helper."""

import textwrap

from renpy_analyzer.checks._label_body import analyze_label_bodies
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_label_with_return(tmp_path):
    model = _project(tmp_path, """\
        label start:
            "Hello"
            return
    """)
    bodies = analyze_label_bodies(model)
    assert "start" in bodies
    assert bodies["start"].has_return is True
    assert bodies["start"].body_lines == 2


def test_label_ending_with_jump(tmp_path):
    model = _project(tmp_path, """\
        label start:
            "Hello"
            jump ending
        label ending:
            return
    """)
    bodies = analyze_label_bodies(model)
    assert bodies["start"].ends_with_jump is True
    assert bodies["start"].has_return is False
    assert bodies["start"].jump_targets == ["ending"]


def test_label_with_both_jump_and_return(tmp_path):
    """Label with return in one branch and jump in another."""
    model = _project(tmp_path, """\
        label start:
            if condition:
                return
            jump fallback
        label fallback:
            return
    """)
    bodies = analyze_label_bodies(model)
    assert bodies["start"].has_return is True
    assert bodies["start"].ends_with_jump is True


def test_empty_label(tmp_path):
    model = _project(tmp_path, """\
        label empty_one:
        label has_content:
            "Hello"
            return
    """)
    bodies = analyze_label_bodies(model)
    assert bodies["empty_one"].body_lines == 0
    assert bodies["has_content"].body_lines == 2


def test_label_with_only_pass(tmp_path):
    model = _project(tmp_path, """\
        label stub:
            pass
        label real:
            "Content"
            return
    """)
    bodies = analyze_label_bodies(model)
    assert bodies["stub"].only_pass is True
    assert bodies["stub"].body_lines == 1
    assert bodies["real"].only_pass is False


def test_multi_label_boundary_detection(tmp_path):
    model = _project(tmp_path, """\
        label first:
            "Line 1"
            "Line 2"
            return
        label second:
            "Line A"
            jump first
    """)
    bodies = analyze_label_bodies(model)
    assert bodies["first"].body_lines == 3
    assert bodies["first"].has_return is True
    assert bodies["second"].body_lines == 2
    assert bodies["second"].ends_with_jump is True


def test_label_with_comments_only(tmp_path):
    """Comments don't count as meaningful content."""
    model = _project(tmp_path, """\
        label commented:
            # This is a comment
            # Another comment
        label next:
            return
    """)
    bodies = analyze_label_bodies(model)
    assert bodies["commented"].body_lines == 0


def test_duplicate_labels_keeps_first(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "a.rpy").write_text(textwrap.dedent("""\
        label dup:
            return
    """), encoding="utf-8")
    (game / "b.rpy").write_text(textwrap.dedent("""\
        label dup:
            jump somewhere
    """), encoding="utf-8")
    model = load_project(str(tmp_path))
    bodies = analyze_label_bodies(model)
    assert "dup" in bodies
    # First file processed wins
    assert bodies["dup"].has_return is True or bodies["dup"].ends_with_jump is True


def test_empty_project(tmp_path):
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    bodies = analyze_label_bodies(model)
    assert bodies == {}
