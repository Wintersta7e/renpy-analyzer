"""Tests for assets check."""
import textwrap

from renpy_analyzer.checks.assets import check
from renpy_analyzer.project import load_project


def _project_with_images(tmp_path, script, images=None):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    if images:
        for path_str in images:
            p = game / path_str
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"fake")
    return load_project(str(tmp_path))


def test_undefined_scene(tmp_path):
    model = _project_with_images(tmp_path, """\
        image ch1_bg = "bg.png"
        label start:
            scene ch1_bg with dissolve
            scene meanwhile with dissolve
    """)
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 1
    assert "meanwhile" in undef[0].title


def test_missing_audio_file_detected(tmp_path):
    """Audio file reference with missing file should be flagged."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent("""\
        label start:
            play sound "sfx/nonexistent.ogg"
    """), encoding="utf-8")
    model = load_project(str(tmp_path))
    findings = check(model)
    audio = [f for f in findings if "audio" in f.title.lower() or "Missing" in f.title]
    assert len(audio) >= 1


def test_builtin_scene_not_flagged(tmp_path):
    model = _project_with_images(tmp_path, """\
        label start:
            scene black with fade
    """)
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 0


def test_empty_model_returns_empty(tmp_path):
    """Assets check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_images_subdir_auto_detection(tmp_path):
    """Files in game/images/ should be auto-registered as image definitions."""
    game = tmp_path / "game"
    game.mkdir()
    # Create image file in images/ subdirectory
    images = game / "images" / "bg"
    images.mkdir(parents=True)
    (images / "park.png").write_bytes(b"fake png")
    (game / "script.rpy").write_text(textwrap.dedent("""\
        label start:
            scene bg park with dissolve
    """), encoding="utf-8")
    model = load_project(str(tmp_path))
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 0


def test_audio_file_exists_no_finding(tmp_path):
    """Audio reference to an existing file should produce no finding."""
    game = tmp_path / "game"
    game.mkdir()
    sfx = game / "sfx"
    sfx.mkdir()
    (sfx / "click.ogg").write_bytes(b"fake audio")
    (game / "script.rpy").write_text(textwrap.dedent("""\
        label start:
            play sound "sfx/click.ogg"
    """), encoding="utf-8")
    model = load_project(str(tmp_path))
    findings = check(model)
    audio = [f for f in findings if "audio" in f.title.lower() or "Missing" in f.title]
    assert len(audio) == 0


def test_audio_case_mismatch(tmp_path):
    """Audio reference with wrong case should produce a case mismatch finding."""
    game = tmp_path / "game"
    game.mkdir()
    sfx = game / "sfx"
    sfx.mkdir()
    (sfx / "Click.ogg").write_bytes(b"fake audio")
    (game / "script.rpy").write_text(textwrap.dedent("""\
        label start:
            play sound "sfx/click.ogg"
    """), encoding="utf-8")
    model = load_project(str(tmp_path))
    findings = check(model)
    case = [f for f in findings if "case mismatch" in f.title.lower()]
    assert len(case) == 1
