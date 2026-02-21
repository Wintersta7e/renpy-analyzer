"""Tests for .rpa archive detection and its effect on checks."""

from renpy_analyzer.checks.assets import check as assets_check
from renpy_analyzer.checks.labels import check as labels_check
from renpy_analyzer.models import (
    Call,
    ImageDef,
    Jump,
    Label,
    MusicRef,
    ProjectModel,
    SceneRef,
    Severity,
)

# ---------------------------------------------------------------------------
# ProjectModel.has_rpa default
# ---------------------------------------------------------------------------


def test_has_rpa_defaults_to_false():
    """ProjectModel.has_rpa should default to False."""
    model = ProjectModel(root_dir="/tmp/fake")
    assert model.has_rpa is False


# ---------------------------------------------------------------------------
# assets.check() with has_rpa=True
# ---------------------------------------------------------------------------


def test_assets_no_undefined_scene_when_rpa(tmp_path):
    """When has_rpa=True, assets.check() should NOT report undefined scene images."""
    model = ProjectModel(root_dir=str(tmp_path), has_rpa=True)
    model.scenes = [
        SceneRef(image_name="mystery_bg", file="script.rpy", line=5),
        SceneRef(image_name="chapter2_bg", file="script.rpy", line=10),
    ]
    findings = assets_check(model)
    undef = [f for f in findings if "Undefined scene image" in f.title]
    assert len(undef) == 0


def test_assets_still_reports_audio_when_rpa(tmp_path):
    """When has_rpa=True, audio/movie file checks should still work."""
    model = ProjectModel(root_dir=str(tmp_path), has_rpa=True)
    model.music = [
        MusicRef(path="sfx/nonexistent.ogg", file="script.rpy", line=3, action="sound"),
    ]
    findings = assets_check(model)
    audio = [f for f in findings if "audio" in f.title.lower() or "Missing" in f.title]
    assert len(audio) >= 1


def test_assets_still_reports_movie_when_rpa(tmp_path):
    """When has_rpa=True, Movie() path checks should still work."""
    model = ProjectModel(root_dir=str(tmp_path), has_rpa=True)
    model.images = [
        ImageDef(
            name="anim",
            file="script.rpy",
            line=1,
            value='Movie(play="movies/nonexistent.webm")',
        ),
    ]
    findings = assets_check(model)
    movie = [f for f in findings if "Missing" in f.title or "Animation" in f.title]
    assert len(movie) >= 1


def test_assets_reports_undefined_scene_without_rpa(tmp_path):
    """When has_rpa=False (default), undefined scene images should still be flagged."""
    model = ProjectModel(root_dir=str(tmp_path), has_rpa=False)
    model.scenes = [
        SceneRef(image_name="mystery_bg", file="script.rpy", line=5),
    ]
    findings = assets_check(model)
    undef = [f for f in findings if "Undefined scene image" in f.title]
    assert len(undef) == 1


# ---------------------------------------------------------------------------
# labels.check() with has_rpa=True
# ---------------------------------------------------------------------------


def test_labels_missing_jump_downgraded_with_rpa():
    """When has_rpa=True, missing jump target should be MEDIUM, not CRITICAL."""
    model = ProjectModel(root_dir="/tmp/fake", has_rpa=True)
    model.labels = [Label(name="start", file="script.rpy", line=1)]
    model.jumps = [Jump(target="nonexistent", file="script.rpy", line=2)]
    findings = labels_check(model)
    missing = [f for f in findings if "Missing label" in f.title]
    assert len(missing) == 1
    assert missing[0].severity == Severity.MEDIUM
    assert ".rpa archives" in missing[0].description


def test_labels_missing_call_downgraded_with_rpa():
    """When has_rpa=True, missing call target should be MEDIUM, not CRITICAL."""
    model = ProjectModel(root_dir="/tmp/fake", has_rpa=True)
    model.labels = [Label(name="start", file="script.rpy", line=1)]
    model.calls = [Call(target="nonexistent", file="script.rpy", line=2)]
    findings = labels_check(model)
    missing = [f for f in findings if "Missing label" in f.title]
    assert len(missing) == 1
    assert missing[0].severity == Severity.MEDIUM
    assert ".rpa archives" in missing[0].description


def test_labels_missing_jump_critical_without_rpa():
    """When has_rpa=False, missing jump target should remain CRITICAL."""
    model = ProjectModel(root_dir="/tmp/fake", has_rpa=False)
    model.labels = [Label(name="start", file="script.rpy", line=1)]
    model.jumps = [Jump(target="nonexistent", file="script.rpy", line=2)]
    findings = labels_check(model)
    missing = [f for f in findings if "Missing label" in f.title]
    assert len(missing) == 1
    assert missing[0].severity == Severity.CRITICAL
    assert ".rpa archives" not in missing[0].description


def test_labels_duplicate_unaffected_by_rpa():
    """Duplicate label findings should NOT be affected by has_rpa."""
    model = ProjectModel(root_dir="/tmp/fake", has_rpa=True)
    model.labels = [
        Label(name="start", file="script.rpy", line=1),
        Label(name="start", file="script.rpy", line=10),
    ]
    findings = labels_check(model)
    dupes = [f for f in findings if "Duplicate" in f.title]
    assert len(dupes) == 2
    assert all(f.severity == Severity.HIGH for f in dupes)


def test_labels_dynamic_jump_unaffected_by_rpa():
    """Dynamic jump findings should NOT be affected by has_rpa."""
    from renpy_analyzer.models import DynamicJump

    model = ProjectModel(root_dir="/tmp/fake", has_rpa=True)
    model.dynamic_jumps = [
        DynamicJump(expression="target_var", file="script.rpy", line=5),
    ]
    findings = labels_check(model)
    dynamic = [f for f in findings if "Dynamic" in f.title]
    assert len(dynamic) == 1
    assert dynamic[0].severity == Severity.MEDIUM


# ---------------------------------------------------------------------------
# project.py .rpa detection (integration)
# ---------------------------------------------------------------------------


def test_load_project_detects_rpa(tmp_path):
    """load_project should set has_rpa=True when .rpa files exist."""
    from renpy_analyzer.project import load_project

    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    (game / "archive.rpa").write_bytes(b"RPA-3.0 fake archive")
    model = load_project(str(tmp_path))
    assert model.has_rpa is True


def test_load_project_no_rpa(tmp_path):
    """load_project should set has_rpa=False when no .rpa files exist."""
    from renpy_analyzer.project import load_project

    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    model = load_project(str(tmp_path))
    assert model.has_rpa is False
