"""Tests for characters check."""
import textwrap

from renpy_analyzer.checks.characters import check
from renpy_analyzer.project import load_project


def _project(tmp_path, defines, script):
    game = tmp_path / "game"
    game.mkdir()
    (game / "defines.rpy").write_text(textwrap.dedent(defines), encoding="utf-8")
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    return load_project(str(tmp_path))


def test_undefined_speaker(tmp_path):
    model = _project(tmp_path, """\
        define mc = Character("Player", color="#fff")
    """, """\
        label start:
            mc "Hello"
            unknown "Who am I?"
    """)
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 1
    assert "unknown" in undef[0].title


def test_unused_character(tmp_path):
    model = _project(tmp_path, """\
        define mc = Character("Player", color="#fff")
        define npc = Character("NPC", color="#aaa")
    """, """\
        label start:
            mc "Hello"
    """)
    findings = check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert len(unused) == 1
    assert "npc" in unused[0].title


def test_all_used_no_findings(tmp_path):
    model = _project(tmp_path, """\
        define mc = Character("Player", color="#fff")
    """, """\
        label start:
            mc "Hello"
    """)
    findings = check(model)
    assert len(findings) == 0


def test_empty_model_returns_empty(tmp_path):
    """Characters check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_multiple_uses_of_undefined_speaker(tmp_path):
    """Undefined speaker used multiple times should mention other locations."""
    model = _project(tmp_path, """\
        define mc = Character("Player", color="#fff")
    """, """\
        label start:
            unknown "First line"
            mc "Hello"
            unknown "Second line"
            unknown "Third line"
    """)
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title and "unknown" in f.title]
    assert len(undef) == 1
    assert "other" in undef[0].description.lower()


def test_character_via_default(tmp_path):
    """Character defined via 'default' should also suppress undefined speaker."""
    model = _project(tmp_path, """\
        default npc = Character("NPC", color="#aaa")
    """, """\
        label start:
            npc "Hello there"
    """)
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 0
