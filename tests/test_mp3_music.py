"""Tests for MP3 looping music check."""

import textwrap

from renpy_analyzer.checks.assets import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_mp3_music_flagged(tmp_path):
    """play music with .mp3 should produce a STYLE finding."""
    model = _project(
        tmp_path,
        """\
        label start:
            play music "audio/bgm.mp3"
    """,
    )
    findings = check(model)
    mp3 = [f for f in findings if "MP3" in f.title]
    assert len(mp3) == 1
    assert mp3[0].severity.name == "STYLE"
    assert "OGG" in mp3[0].suggestion


def test_ogg_music_not_flagged(tmp_path):
    """play music with .ogg should NOT be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            play music "audio/bgm.ogg"
    """,
    )
    findings = check(model)
    mp3 = [f for f in findings if "MP3" in f.title]
    assert len(mp3) == 0


def test_mp3_sound_not_flagged(tmp_path):
    """play sound with .mp3 should NOT be flagged (sounds don't loop)."""
    model = _project(
        tmp_path,
        """\
        label start:
            play sound "sfx/click.mp3"
    """,
    )
    findings = check(model)
    mp3 = [f for f in findings if "MP3" in f.title]
    assert len(mp3) == 0


def test_mp3_queue_flagged(tmp_path):
    """queue music with .mp3 should also be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            queue music "audio/bgm2.mp3"
    """,
    )
    findings = check(model)
    mp3 = [f for f in findings if "MP3" in f.title]
    assert len(mp3) == 1
