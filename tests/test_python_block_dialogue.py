"""Tests for python block dialogue suppression in the parser.

Verifies that strings inside init python: and python: blocks are NOT
parsed as dialogue/narrator lines.
"""

import textwrap
from pathlib import Path

from renpy_analyzer.parser import parse_file


def _write_rpy(tmp_path: Path, content: str) -> str:
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


def test_init_python_dict_not_dialogue(tmp_path):
    """Dict literal inside init python: should not match as dialogue."""
    path = _write_rpy(
        tmp_path,
        """\
        init python:
            character_data = {
                "yurika": {
                    "name": "Yurika",
                    "color": "#ff69b4",
                },
                "tsubasa": {
                    "name": "Tsubasa",
                },
            }
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_init_python_string_assign_not_dialogue(tmp_path):
    """String assignments in init python: should not match as narrator."""
    path = _write_rpy(
        tmp_path,
        """\
        init python:
            greeting = "Hello world"
            title = "My Game"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_standalone_python_block_not_dialogue(tmp_path):
    """Strings inside standalone python: blocks should not match as dialogue."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            python:
                data = {
                    "key": "value",
                }
                msg = "test message"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_dialogue_outside_python_still_works(tmp_path):
    """Normal dialogue lines should still be captured."""
    path = _write_rpy(
        tmp_path,
        """\
        init python:
            greeting = "Hello"

        label start:
            y "Hello there!"
            "Narrator text"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 2
    speakers = [d.speaker for d in result["dialogue"]]
    assert "y" in speakers
    assert "" in speakers  # narrator


def test_init_python_with_priority_not_dialogue(tmp_path):
    """init -1 python: blocks should also suppress dialogue."""
    path = _write_rpy(
        tmp_path,
        """\
        init -1 python:
            my_dict = {
                "alice": "character",
            }
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_init_label_allows_dialogue(tmp_path):
    """init: blocks (without python) contain Ren'Py statements, dialogue is OK."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            y "Hello from a label"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 1


def test_python_hide_block_not_dialogue(tmp_path):
    """python hide: blocks should suppress dialogue matching."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            python hide:
                msg = "this is not dialogue"
                data = {"key": "value"}
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_python_in_store_block_not_dialogue(tmp_path):
    """python in mystore: blocks should suppress dialogue matching."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            python in mystore:
                greeting = "hello"
                items = {"sword": 10}
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_init_python_hide_not_dialogue(tmp_path):
    """init python hide: blocks should suppress dialogue matching."""
    path = _write_rpy(
        tmp_path,
        """\
        init python hide:
            config = {"debug": True}
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_init_python_in_store_not_dialogue(tmp_path):
    """init python in mystore: blocks should suppress dialogue matching."""
    path = _write_rpy(
        tmp_path,
        """\
        init python in mystore:
            defaults = {"name": "Player"}
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 0


def test_python_block_with_if_not_dialogue(tmp_path):
    """python: inside an if block within a label should suppress dialogue."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            if True:
                python:
                    name = "test"
            y "Real dialogue"
    """,
    )
    result = parse_file(path)
    assert len(result["dialogue"]) == 1
    assert result["dialogue"][0].speaker == "y"
