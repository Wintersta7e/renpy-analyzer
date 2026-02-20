"""Tests for project loader."""

import textwrap
from pathlib import Path

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
