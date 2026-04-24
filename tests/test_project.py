"""Tests for project loader."""

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from renpy_analyzer.project import load_project


def _make_project(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            jump chapter1
        label chapter1:
            mc "Hello"
            jump ending
    """),
        encoding="utf-8",
    )
    (game / "variables.rpy").write_text(
        textwrap.dedent("""\
        default Lydia = 0
        default Barb = 0
    """),
        encoding="utf-8",
    )
    return tmp_path


def test_load_project_auto_finds_game_dir(tmp_path):
    root = _make_project(tmp_path)
    model = load_project(str(root))
    assert len(model.files) == 2
    assert len(model.labels) == 2
    assert len(model.jumps) == 2
    assert len(model.variables) == 2


def test_load_project_relative_paths(tmp_path):
    root = _make_project(tmp_path)
    model = load_project(str(root))
    for label in model.labels:
        assert not label.file.startswith("/")
        assert not label.file.startswith("\\")


# --- Edge case tests ---


def test_load_empty_project(tmp_path):
    """A project with no .rpy files should return empty model, not crash."""
    game = tmp_path / "game"
    game.mkdir()
    model = load_project(str(tmp_path))
    assert model.files == []
    assert model.labels == []
    assert model.jumps == []
    assert model.variables == []


def test_load_project_no_game_subdir(tmp_path):
    """When no game/ subdir exists, scan the directory itself."""
    (tmp_path / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            jump ending
        label ending:
            return
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    assert len(model.labels) == 2
    assert model.root_dir == str(tmp_path)


def test_load_project_nested_files(tmp_path):
    """Nested .rpy files in subdirectories should be found and loaded."""
    game = tmp_path / "game"
    game.mkdir()
    subdir = game / "scripts" / "chapter1"
    subdir.mkdir(parents=True)
    (subdir / "ch1.rpy").write_text(
        textwrap.dedent("""\
        label ch1_start:
            "Chapter 1"
    """),
        encoding="utf-8",
    )
    (game / "main.rpy").write_text(
        textwrap.dedent("""\
        label start:
            jump ch1_start
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    assert len(model.files) == 2
    assert len(model.labels) == 2
    # Nested file should have relative path with subdir
    nested_label = next(lbl for lbl in model.labels if lbl.name == "ch1_start")
    assert "scripts" in nested_label.file or "chapter1" in nested_label.file


def test_load_project_files_are_absolute(tmp_path):
    """model.files should contain absolute paths."""
    root = _make_project(tmp_path)
    model = load_project(str(root))
    for f in model.files:
        assert Path(f).is_absolute()


def test_engine_files_excluded(tmp_path):
    """renpy/ engine files should be excluded from scanning."""
    # Simulate multi-subdir layout (no top-level game/)
    season1 = tmp_path / "Season1"
    game1 = season1 / "game"
    game1.mkdir(parents=True)
    (game1 / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            "Hello"
            return
    """),
        encoding="utf-8",
    )
    # Simulate renpy/common engine files
    renpy_common = season1 / "renpy" / "common"
    renpy_common.mkdir(parents=True)
    (renpy_common / "00gamemenu.rpy").write_text(
        textwrap.dedent("""\
        label _enter_game_menu:
            call _enter_game_menu
            return
    """),
        encoding="utf-8",
    )
    (renpy_common / "00achievement.rpy").write_text(
        textwrap.dedent("""\
        default persistent._achievements = {}
        default persistent._achievement_progress = {}
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    # Only user code should be loaded
    assert len(model.files) == 1
    assert any("script.rpy" in f for f in model.files)
    assert not any("renpy" in f for f in model.files)
    # Only user labels/vars, no engine data
    assert len(model.labels) == 1
    assert model.labels[0].name == "start"


def test_engine_files_excluded_flat_layout(tmp_path):
    """Even in flat layout (game/ exists), renpy/ siblings aren't scanned.

    In flat layout, scan_dir is game/, so renpy/ is a sibling and not
    included in rglob anyway.  But verify the filter doesn't break this.
    """
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    renpy_common = tmp_path / "renpy" / "common"
    renpy_common.mkdir(parents=True)
    (renpy_common / "engine.rpy").write_text("label _engine:\n    return\n", encoding="utf-8")
    model = load_project(str(tmp_path))
    assert len(model.files) == 1
    assert len(model.labels) == 1


def test_load_project_skips_symlinked_rpy_files(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    outside = tmp_path / "outside.rpy"
    outside.write_text("label escaped:\n    return\n", encoding="utf-8")

    try:
        (game / "escape.rpy").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform")

    model = load_project(str(tmp_path))

    assert [label.name for label in model.labels] == ["start"]
    assert [Path(path).name for path in model.files] == ["script.rpy"]


def test_load_project_skips_symlinked_script_directories(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "escaped.rpy").write_text("label escaped:\n    return\n", encoding="utf-8")

    try:
        (game / "linked").symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform")

    model = load_project(str(tmp_path))

    assert [label.name for label in model.labels] == ["start"]
    assert [Path(path).name for path in model.files] == ["script.rpy"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo is unavailable on this platform")
def test_load_project_skips_named_pipe_scripts(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    os.mkfifo(game / "blocked.rpy")

    model = load_project(str(tmp_path))

    assert [Path(path).name for path in model.files] == ["script.rpy"]
    assert [label.name for label in model.labels] == ["start"]


def test_load_project_unsafe_rpyc_artifact_does_not_set_compiled_only(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    outside = tmp_path / "outside.rpyc"
    outside.write_bytes(b"\x00" * 8)

    try:
        (game / "escaped.rpyc").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform")

    model = load_project(str(tmp_path))

    assert model.files == []
    assert model.has_rpyc_only is False


def test_load_project_sdk_parser_receives_only_validated_files(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    safe_script = game / "script.rpy"
    safe_script.write_text("label start:\n    return\n", encoding="utf-8")
    outside = tmp_path / "outside.rpy"
    outside.write_text("label escaped:\n    return\n", encoding="utf-8")

    try:
        (game / "escape.rpy").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform")

    with (
        patch(
            "renpy_analyzer.sdk_bridge.parse_files_with_sdk",
            return_value={str(safe_script): {}},
        ) as mock_parse,
        patch("renpy_analyzer.sdk_bridge.convert_file_result", return_value={}),
    ):
        load_project(str(tmp_path), sdk_path="/trusted/sdk", trust_sdk=True)

    assert mock_parse.call_args is not None
    assert mock_parse.call_args.args[0] == [str(safe_script)]
    assert mock_parse.call_args.kwargs["trust_sdk"] is True
