"""Tests for project loader."""

import textwrap
from pathlib import Path

from renpy_analyzer.project import load_project


def _make_project(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent("""\
        label start:
            jump chapter1
        label chapter1:
            mc "Hello"
            jump ending
    """), encoding="utf-8")
    (game / "variables.rpy").write_text(textwrap.dedent("""\
        default Lydia = 0
        default Barb = 0
    """), encoding="utf-8")
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
