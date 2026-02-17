"""Tests for assets check."""
import textwrap
from renpy_analyzer.project import load_project
from renpy_analyzer.checks.assets import check
from renpy_analyzer.models import Severity


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


def test_builtin_scene_not_flagged(tmp_path):
    model = _project_with_images(tmp_path, """\
        label start:
            scene black with fade
    """)
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 0
