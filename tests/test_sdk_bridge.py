"""Tests for sdk_bridge.py — host-side subprocess management + JSON→model conversion."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from renpy_analyzer.models import (
    Call,
    CharacterDef,
    Condition,
    DialogueLine,
    DynamicJump,
    ImageDef,
    Jump,
    Label,
    Menu,
    MusicRef,
    SceneRef,
    ShowRef,
    Variable,
)
from renpy_analyzer.sdk_bridge import (
    convert_file_result,
    find_sdk_python,
    parse_files_with_sdk,
    validate_sdk_path,
)

# ---------------------------------------------------------------------------
# validate_sdk_path
# ---------------------------------------------------------------------------


def test_validate_sdk_path_missing_dir(tmp_path):
    assert validate_sdk_path(str(tmp_path / "nonexistent")) is False


def test_validate_sdk_path_no_renpy_dir(tmp_path):
    assert validate_sdk_path(str(tmp_path)) is False


def test_validate_sdk_path_valid(tmp_path):
    (tmp_path / "renpy").mkdir()
    py_dir = tmp_path / "lib" / "py3-linux-x86_64"
    py_dir.mkdir(parents=True)
    py_bin = py_dir / "python"
    py_bin.write_text("#!/bin/sh\n")
    py_bin.chmod(0o755)
    assert validate_sdk_path(str(tmp_path)) is True


def test_validate_sdk_path_no_python(tmp_path):
    (tmp_path / "renpy").mkdir()
    assert validate_sdk_path(str(tmp_path)) is False


# ---------------------------------------------------------------------------
# find_sdk_python
# ---------------------------------------------------------------------------


def test_find_sdk_python_linux(tmp_path):
    (tmp_path / "renpy").mkdir()
    py_dir = tmp_path / "lib" / "py3-linux-x86_64"
    py_dir.mkdir(parents=True)
    py_bin = py_dir / "python"
    py_bin.write_text("#!/bin/sh\n")

    with patch("renpy_analyzer.sdk_bridge.platform") as mock_platform:
        mock_platform.system.return_value = "Linux"
        result = find_sdk_python(str(tmp_path))
        assert result == str(py_bin)


def test_find_sdk_python_fallback_glob(tmp_path):
    """Should find Python via glob when platform doesn't match exactly."""
    (tmp_path / "renpy").mkdir()
    py_dir = tmp_path / "lib" / "py3-custom-arch"
    py_dir.mkdir(parents=True)
    py_bin = py_dir / "python3"
    py_bin.write_text("#!/bin/sh\n")

    with patch("renpy_analyzer.sdk_bridge.platform") as mock_platform:
        mock_platform.system.return_value = "Linux"
        result = find_sdk_python(str(tmp_path))
        assert "python3" in result


def test_find_sdk_python_not_found(tmp_path):
    with pytest.raises(RuntimeError, match="Could not find SDK Python"):
        find_sdk_python(str(tmp_path))


# ---------------------------------------------------------------------------
# convert_file_result — JSON dicts → model dataclasses
# ---------------------------------------------------------------------------


def test_convert_labels():
    data = {"labels": [{"name": "start", "line": 1}, {"name": "ending", "line": 20}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["labels"]) == 2
    assert isinstance(result["labels"][0], Label)
    assert result["labels"][0].name == "start"
    assert result["labels"][0].line == 1
    assert result["labels"][0].file == "script.rpy"


def test_convert_jumps():
    data = {"jumps": [{"target": "ch2", "line": 5}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["jumps"]) == 1
    assert isinstance(result["jumps"][0], Jump)
    assert result["jumps"][0].target == "ch2"


def test_convert_calls():
    data = {"calls": [{"target": "helper", "line": 10}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["calls"]) == 1
    assert isinstance(result["calls"][0], Call)
    assert result["calls"][0].target == "helper"


def test_convert_dynamic_jumps():
    data = {"dynamic_jumps": [{"expression": "next_label", "line": 15}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["dynamic_jumps"]) == 1
    assert isinstance(result["dynamic_jumps"][0], DynamicJump)
    assert result["dynamic_jumps"][0].expression == "next_label"


def test_convert_variables():
    data = {
        "variables": [
            {"name": "score", "line": 3, "kind": "default", "value": "0"},
            {"name": "flags", "line": 5, "kind": "assign", "value": "{}"},
        ]
    }
    result = convert_file_result(data, "vars.rpy")
    assert len(result["variables"]) == 2
    assert isinstance(result["variables"][0], Variable)
    assert result["variables"][0].name == "score"
    assert result["variables"][0].kind == "default"
    assert result["variables"][1].kind == "assign"


def test_convert_menus():
    data = {
        "menus": [
            {
                "line": 10,
                "choices": [
                    {
                        "text": "Go left",
                        "line": 11,
                        "content_lines": 2,
                        "has_jump": True,
                        "has_return": False,
                        "condition": None,
                    },
                    {
                        "text": "Go right",
                        "line": 14,
                        "content_lines": 1,
                        "has_jump": False,
                        "has_return": False,
                        "condition": "has_key",
                    },
                ],
            }
        ]
    }
    result = convert_file_result(data, "script.rpy")
    assert len(result["menus"]) == 1
    menu = result["menus"][0]
    assert isinstance(menu, Menu)
    assert len(menu.choices) == 2
    assert menu.choices[0].text == "Go left"
    assert menu.choices[0].has_jump is True
    assert menu.choices[1].condition == "has_key"


def test_convert_scenes():
    data = {
        "scenes": [
            {"image_name": "bg park day", "line": 8, "transition": "dissolve"},
        ]
    }
    result = convert_file_result(data, "script.rpy")
    assert len(result["scenes"]) == 1
    assert isinstance(result["scenes"][0], SceneRef)
    assert result["scenes"][0].image_name == "bg park day"
    assert result["scenes"][0].transition == "dissolve"


def test_convert_shows():
    data = {"shows": [{"image_name": "eileen happy", "line": 12}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["shows"]) == 1
    assert isinstance(result["shows"][0], ShowRef)
    assert result["shows"][0].image_name == "eileen happy"


def test_convert_images():
    data = {"images": [{"name": "bg park", "line": 2, "value": '"bg/park.png"'}]}
    result = convert_file_result(data, "images.rpy")
    assert len(result["images"]) == 1
    assert isinstance(result["images"][0], ImageDef)
    assert result["images"][0].name == "bg park"


def test_convert_music():
    data = {
        "music": [
            {"path": "audio/bgm.ogg", "line": 5, "action": "play"},
            {"path": "", "line": 20, "action": "stop"},
        ]
    }
    result = convert_file_result(data, "script.rpy")
    assert len(result["music"]) == 2
    assert isinstance(result["music"][0], MusicRef)
    assert result["music"][0].path == "audio/bgm.ogg"
    assert result["music"][1].action == "stop"


def test_convert_characters():
    data = {
        "characters": [
            {"shorthand": "mc", "display_name": "Alex", "line": 1},
        ]
    }
    result = convert_file_result(data, "chars.rpy")
    assert len(result["characters"]) == 1
    assert isinstance(result["characters"][0], CharacterDef)
    assert result["characters"][0].shorthand == "mc"
    assert result["characters"][0].display_name == "Alex"


def test_convert_dialogue():
    data = {"dialogue": [{"speaker": "mc", "line": 10}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["dialogue"]) == 1
    assert isinstance(result["dialogue"][0], DialogueLine)
    assert result["dialogue"][0].speaker == "mc"


def test_convert_conditions():
    data = {"conditions": [{"expression": "score > 50", "line": 30}]}
    result = convert_file_result(data, "script.rpy")
    assert len(result["conditions"]) == 1
    assert isinstance(result["conditions"][0], Condition)
    assert result["conditions"][0].expression == "score > 50"


def test_convert_empty_data():
    """Empty or missing keys should produce empty lists, not errors."""
    result = convert_file_result({}, "script.rpy")
    for key in [
        "labels",
        "jumps",
        "calls",
        "dynamic_jumps",
        "variables",
        "menus",
        "scenes",
        "shows",
        "images",
        "music",
        "characters",
        "dialogue",
        "conditions",
    ]:
        assert result[key] == []


def test_convert_full_file():
    """A realistic file result with multiple element types."""
    data = {
        "labels": [{"name": "start", "line": 1}],
        "jumps": [{"target": "ch2", "line": 5}],
        "calls": [{"target": "helper", "line": 3}],
        "dynamic_jumps": [],
        "variables": [{"name": "score", "line": 2, "kind": "default", "value": "0"}],
        "menus": [],
        "scenes": [{"image_name": "bg room", "line": 4, "transition": None}],
        "shows": [{"image_name": "eileen happy", "line": 6}],
        "images": [],
        "music": [{"path": "audio/theme.ogg", "line": 7, "action": "play"}],
        "characters": [{"shorthand": "e", "display_name": "Eileen", "line": 1}],
        "dialogue": [{"speaker": "e", "line": 8}],
        "conditions": [{"expression": "score > 10", "line": 9}],
    }
    result = convert_file_result(data, "game/script.rpy")
    assert len(result["labels"]) == 1
    assert len(result["jumps"]) == 1
    assert len(result["calls"]) == 1
    assert len(result["variables"]) == 1
    assert len(result["scenes"]) == 1
    assert len(result["shows"]) == 1
    assert len(result["music"]) == 1
    assert len(result["characters"]) == 1
    assert len(result["dialogue"]) == 1
    assert len(result["conditions"]) == 1
    # All items should have the correct file path
    assert result["labels"][0].file == "game/script.rpy"
    assert result["scenes"][0].file == "game/script.rpy"


# ---------------------------------------------------------------------------
# parse_files_with_sdk — subprocess management (mocked)
# ---------------------------------------------------------------------------


def _make_response(results=None, errors=None, success=True, version="8.5.2"):
    return json.dumps(
        {
            "success": success,
            "version": version,
            "results": results or {},
            "errors": errors or [],
        }
    )


@patch("renpy_analyzer.sdk_bridge._find_bridge_worker")
@patch("renpy_analyzer.sdk_bridge.find_sdk_python")
@patch("renpy_analyzer.sdk_bridge.subprocess.run")
def test_parse_files_success(mock_run, mock_find_py, mock_find_worker):
    mock_find_py.return_value = "/sdk/lib/py3-linux/python"
    mock_find_worker.return_value = "/path/to/bridge_worker.py"

    file_data = {
        "/game/script.rpy": {
            "labels": [{"name": "start", "line": 1}],
            "jumps": [],
            "calls": [],
            "dynamic_jumps": [],
            "variables": [],
            "menus": [],
            "scenes": [],
            "shows": [],
            "images": [],
            "music": [],
            "characters": [],
            "dialogue": [],
            "conditions": [],
        }
    }
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_response(results=file_data),
        stderr="",
    )

    result = parse_files_with_sdk(["/game/script.rpy"], "/game", "/sdk")
    assert "/game/script.rpy" in result
    assert result["/game/script.rpy"]["labels"][0]["name"] == "start"


@patch("renpy_analyzer.sdk_bridge._find_bridge_worker")
@patch("renpy_analyzer.sdk_bridge.find_sdk_python")
@patch("renpy_analyzer.sdk_bridge.subprocess.run")
def test_parse_files_timeout(mock_run, mock_find_py, mock_find_worker):
    mock_find_py.return_value = "/sdk/lib/py3-linux/python"
    mock_find_worker.return_value = "/path/to/bridge_worker.py"
    import subprocess

    mock_run.side_effect = subprocess.TimeoutExpired(cmd="python", timeout=120)

    with pytest.raises(RuntimeError, match="timed out"):
        parse_files_with_sdk(["/game/script.rpy"], "/game", "/sdk")


@patch("renpy_analyzer.sdk_bridge._find_bridge_worker")
@patch("renpy_analyzer.sdk_bridge.find_sdk_python")
@patch("renpy_analyzer.sdk_bridge.subprocess.run")
def test_parse_files_nonzero_exit(mock_run, mock_find_py, mock_find_worker):
    mock_find_py.return_value = "/sdk/lib/py3-linux/python"
    mock_find_worker.return_value = "/path/to/bridge_worker.py"
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="ImportError: No module named renpy",
    )

    with pytest.raises(RuntimeError, match="exited with code 1"):
        parse_files_with_sdk(["/game/script.rpy"], "/game", "/sdk")


@patch("renpy_analyzer.sdk_bridge._find_bridge_worker")
@patch("renpy_analyzer.sdk_bridge.find_sdk_python")
@patch("renpy_analyzer.sdk_bridge.subprocess.run")
def test_parse_files_invalid_json(mock_run, mock_find_py, mock_find_worker):
    mock_find_py.return_value = "/sdk/lib/py3-linux/python"
    mock_find_worker.return_value = "/path/to/bridge_worker.py"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="not json at all",
        stderr="",
    )

    with pytest.raises(RuntimeError, match="Invalid JSON"):
        parse_files_with_sdk(["/game/script.rpy"], "/game", "/sdk")


@patch("renpy_analyzer.sdk_bridge._find_bridge_worker")
@patch("renpy_analyzer.sdk_bridge.find_sdk_python")
@patch("renpy_analyzer.sdk_bridge.subprocess.run")
def test_parse_files_sdk_failure(mock_run, mock_find_py, mock_find_worker):
    mock_find_py.return_value = "/sdk/lib/py3-linux/python"
    mock_find_worker.return_value = "/path/to/bridge_worker.py"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_make_response(success=False, errors=[{"file": "", "message": "SDK init failed"}]),
        stderr="",
    )

    with pytest.raises(RuntimeError, match="SDK parser failed"):
        parse_files_with_sdk(["/game/script.rpy"], "/game", "/sdk")


@patch("renpy_analyzer.sdk_bridge._find_bridge_worker")
@patch("renpy_analyzer.sdk_bridge.find_sdk_python")
@patch("renpy_analyzer.sdk_bridge.subprocess.run")
def test_parse_files_os_error(mock_run, mock_find_py, mock_find_worker):
    mock_find_py.return_value = "/sdk/lib/py3-linux/python"
    mock_find_worker.return_value = "/path/to/bridge_worker.py"
    mock_run.side_effect = OSError("No such file")

    with pytest.raises(RuntimeError, match="Failed to launch"):
        parse_files_with_sdk(["/game/script.rpy"], "/game", "/sdk")
