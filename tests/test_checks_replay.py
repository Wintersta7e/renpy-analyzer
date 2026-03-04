"""Tests for replay label check."""

import textwrap

from renpy_analyzer.checks.replay import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content, screen_content=""):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    if screen_content:
        (game / "screens.rpy").write_text(textwrap.dedent(screen_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_replay_missing_end_replay(tmp_path):
    """Replay label without end_replay() should be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"

        label replay_scene1:
            "Some scene content"
            return
    """,
        screen_content="""\
screen gallery():
    textbutton "Scene 1" action Replay("replay_scene1")
    """,
    )
    findings = check(model)
    assert len(findings) == 1
    assert "end_replay" in findings[0].title
    assert findings[0].severity.name == "HIGH"


def test_replay_with_end_replay(tmp_path):
    """Replay label with end_replay() should not be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"

        label replay_scene1:
            "Some scene content"
            $ renpy.end_replay()
            return
    """,
        screen_content="""\
screen gallery():
    textbutton "Scene 1" action Replay("replay_scene1")
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_no_replay_refs(tmp_path):
    """No Replay() references should produce no findings."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_replay_single_quotes(tmp_path):
    """Replay('label') with single quotes should also be detected."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"

        label replay_scene2:
            "Scene 2"
            return
    """,
        screen_content="""\
screen gallery():
    textbutton "Scene 2" action Replay('replay_scene2')
    """,
    )
    findings = check(model)
    assert len(findings) == 1
    assert "replay_scene2" in findings[0].title
