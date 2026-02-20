"""Tests for bridge_worker.py standalone logic — no SDK required.

We import and test the pure-Python helper functions directly:
regex patterns, extract_from_node (with mock AST nodes), merge_results, etc.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

# bridge_worker is standalone, import it via path manipulation
sys.path.insert(0, "src/renpy_analyzer")
from renpy_analyzer.bridge_worker import (
    RE_ASSIGN,
    RE_AUGMENTED,
    RE_CHARACTER,
    RE_PLAY,
    RE_QUEUE,
    RE_STOP,
    RE_VOICE,
    _extract_music,
    extract_from_node,
    flatten_ast,
    merge_results,
)

# ---------------------------------------------------------------------------
# Regex pattern tests
# ---------------------------------------------------------------------------


class TestRegexPatterns:
    def test_assign_simple(self):
        m = RE_ASSIGN.match("    score = 0")
        assert m
        assert m.group(1) == "score"
        assert m.group(2) == "0"

    def test_assign_augmented(self):
        m = RE_AUGMENTED.match("    score += 10")
        assert m
        assert m.group(1) == "score"
        assert m.group(2) == "+="
        assert m.group(3) == "10"

    def test_play_music(self):
        m = RE_PLAY.match('    play music "audio/bgm.ogg"')
        assert m
        assert m.group(1) == "music"
        assert m.group(2) == "audio/bgm.ogg"

    def test_play_sound(self):
        m = RE_PLAY.match('    play sound "sfx/click.wav"')
        assert m
        assert m.group(1) == "sound"

    def test_play_voice(self):
        m = RE_PLAY.match('    play voice "voice/line1.ogg"')
        assert m
        assert m.group(1) == "voice"

    def test_queue_music(self):
        m = RE_QUEUE.match('    queue music "audio/next.ogg"')
        assert m
        assert m.group(2) == "audio/next.ogg"

    def test_voice_standalone(self):
        m = RE_VOICE.match('    voice "voice/line.ogg"')
        assert m
        assert m.group(1) == "voice/line.ogg"

    def test_stop_music(self):
        m = RE_STOP.match("    stop music")
        assert m
        assert m.group(1) == "music"

    def test_character_pattern(self):
        m = RE_CHARACTER.search("Character('Eileen', color='#ff0000')")
        assert m
        assert m.group(1) == "Eileen"

    def test_character_double_quotes(self):
        m = RE_CHARACTER.search('Character("Alex")')
        assert m
        assert m.group(1) == "Alex"


# ---------------------------------------------------------------------------
# Mock AST node helpers
# ---------------------------------------------------------------------------


def _mock_node(cls_name, **attrs):
    """Create a mock AST node with given class name and attributes."""
    node = MagicMock()
    type(node).__name__ = cls_name
    for key, val in attrs.items():
        setattr(node, key, val)
    # Default linenumber
    if "linenumber" not in attrs:
        node.linenumber = 1
    return node


# ---------------------------------------------------------------------------
# extract_from_node tests
# ---------------------------------------------------------------------------


class TestExtractFromNode:
    def test_label(self):
        node = _mock_node("Label", name="start", linenumber=5)
        result = extract_from_node(node, None)
        assert len(result["labels"]) == 1
        assert result["labels"][0] == {"name": "start", "line": 5}

    def test_jump(self):
        node = _mock_node("Jump", target="ch2", expression=False, linenumber=10)
        result = extract_from_node(node, None)
        assert len(result["jumps"]) == 1
        assert result["jumps"][0] == {"target": "ch2", "line": 10}

    def test_jump_expression(self):
        node = _mock_node("Jump", target="next_label", expression=True, linenumber=10)
        result = extract_from_node(node, None)
        assert len(result["dynamic_jumps"]) == 1
        assert result["dynamic_jumps"][0]["expression"] == "next_label"

    def test_call(self):
        node = _mock_node("Call", label="helper", expression=False, linenumber=15)
        result = extract_from_node(node, None)
        assert len(result["calls"]) == 1
        assert result["calls"][0] == {"target": "helper", "line": 15}

    def test_call_expression(self):
        node = _mock_node("Call", label="computed", expression=True, linenumber=15)
        result = extract_from_node(node, None)
        assert len(result["dynamic_jumps"]) == 1

    def test_say(self):
        node = _mock_node("Say", who="mc", what="Hello", linenumber=20)
        result = extract_from_node(node, None)
        assert len(result["dialogue"]) == 1
        assert result["dialogue"][0] == {"speaker": "mc", "line": 20, "text": "Hello"}

    def test_say_narrator(self):
        """Narrator lines (who=None) should not produce dialogue entries."""
        node = _mock_node("Say", who=None, what="Narration", linenumber=20)
        result = extract_from_node(node, None)
        assert len(result["dialogue"]) == 0

    def test_scene(self):
        node = _mock_node("Scene", imspec=(("bg", "park", "day"), (), (), None, None, None), linenumber=8)
        result = extract_from_node(node, None)
        assert len(result["scenes"]) == 1
        assert result["scenes"][0]["image_name"] == "bg park day"

    def test_scene_with_transition(self):
        node = _mock_node("Scene", imspec=(("bg", "room"), (), (), "dissolve", None, None), linenumber=8)
        result = extract_from_node(node, None)
        assert result["scenes"][0]["transition"] == "dissolve"

    def test_show(self):
        node = _mock_node("Show", imspec=(("eileen", "happy"), (), ()), linenumber=12)
        result = extract_from_node(node, None)
        assert len(result["shows"]) == 1
        assert result["shows"][0]["image_name"] == "eileen happy"

    def test_image(self):
        code = MagicMock()
        code.source = '"images/bg_park.png"'
        node = _mock_node("Image", imgname=("bg", "park"), code=code, linenumber=2)
        result = extract_from_node(node, None)
        assert len(result["images"]) == 1
        assert result["images"][0]["name"] == "bg park"
        assert result["images"][0]["value"] == '"images/bg_park.png"'

    def test_define_variable(self):
        code = MagicMock()
        code.source = "42"
        node = _mock_node("Define", varname="max_score", store="store", code=code, linenumber=3)
        result = extract_from_node(node, None)
        assert len(result["variables"]) == 1
        assert result["variables"][0]["name"] == "max_score"
        assert result["variables"][0]["kind"] == "define"

    def test_define_character(self):
        code = MagicMock()
        code.source = "Character('Eileen', color='#ff0000')"
        node = _mock_node("Define", varname="e", store="store", code=code, linenumber=1)
        result = extract_from_node(node, None)
        assert len(result["variables"]) == 1
        assert len(result["characters"]) == 1
        assert result["characters"][0]["shorthand"] == "e"
        assert result["characters"][0]["display_name"] == "Eileen"

    def test_default_variable(self):
        code = MagicMock()
        code.source = "0"
        node = _mock_node("Default", varname="score", store="store", code=code, linenumber=5)
        result = extract_from_node(node, None)
        assert len(result["variables"]) == 1
        assert result["variables"][0]["kind"] == "default"

    def test_define_nondefault_store(self):
        """Variables in non-default stores get prefixed."""
        code = MagicMock()
        code.source = "True"
        node = _mock_node("Define", varname="debug", store="persistent", code=code, linenumber=1)
        result = extract_from_node(node, None)
        assert result["variables"][0]["name"] == "persistent.debug"

    def test_python_block_assignments(self):
        code = MagicMock()
        code.source = "score = 0\nflags = {}\ncount += 1"
        node = _mock_node("Python", code=code, linenumber=10)
        result = extract_from_node(node, None)
        assert len(result["variables"]) == 3
        kinds = [v["kind"] for v in result["variables"]]
        assert "assign" in kinds
        assert "augment" in kinds

    def test_user_statement_play_music(self):
        node = _mock_node("UserStatement", line='play music "audio/bgm.ogg"', linenumber=5)
        result = extract_from_node(node, None)
        assert len(result["music"]) == 1
        assert result["music"][0]["path"] == "audio/bgm.ogg"

    def test_menu_with_choices(self):
        # Menu items: (label, condition, block)
        child_jump = _mock_node("Jump", target="left_path", expression=False, linenumber=12)
        child_say = _mock_node("Say", who="mc", what="ok", linenumber=15)

        node = _mock_node(
            "Menu",
            items=[
                ("Go left", None, [child_jump]),
                ("Go right", "has_key", [child_say]),
                ("Caption text", None, None),  # caption, not a choice
            ],
            linenumber=10,
        )
        result = extract_from_node(node, None)
        assert len(result["menus"]) == 1
        menu = result["menus"][0]
        assert len(menu["choices"]) == 2
        assert menu["choices"][0]["text"] == "Go left"
        assert menu["choices"][0]["has_jump"] is True
        assert menu["choices"][1]["condition"] == "has_key"

    def test_if_conditions(self):
        node = _mock_node(
            "If",
            entries=[
                ("score > 50", []),
                ("True", []),  # else branch
            ],
            linenumber=30,
        )
        result = extract_from_node(node, None)
        assert len(result["conditions"]) == 2
        assert result["conditions"][0]["expression"] == "score > 50"

    def test_return_produces_nothing(self):
        node = _mock_node("Return", linenumber=99)
        result = extract_from_node(node, None)
        for key in result:
            assert result[key] == []

    def test_unknown_node_produces_nothing(self):
        node = _mock_node("SomeUnknownNodeType", linenumber=1)
        result = extract_from_node(node, None)
        for key in result:
            assert result[key] == []


# ---------------------------------------------------------------------------
# flatten_ast
# ---------------------------------------------------------------------------


def test_flatten_ast_single():
    """Node without get_children should return just itself."""
    node = _mock_node("Label", name="test")
    del node.get_children  # no children method
    result = flatten_ast(node)
    assert len(result) == 1


def test_flatten_ast_with_children():
    """get_children uses visitor pattern: calls f(child) for each child."""
    child1 = _mock_node("Say", who="mc")
    del child1.get_children
    child2 = _mock_node("Jump", target="end")
    del child2.get_children

    parent = _mock_node("Label", name="start")

    # Simulate Ren'Py visitor pattern: get_children(f) calls f on self + children
    def fake_get_children(f):
        f(parent)
        f(child1)
        f(child2)

    parent.get_children = fake_get_children

    result = flatten_ast(parent)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# merge_results
# ---------------------------------------------------------------------------


def test_merge_results():
    target = {"labels": [{"name": "a"}], "jumps": []}
    source = {"labels": [{"name": "b"}], "jumps": [{"target": "c"}]}
    merge_results(target, source)
    assert len(target["labels"]) == 2
    assert len(target["jumps"]) == 1


# ---------------------------------------------------------------------------
# _extract_music
# ---------------------------------------------------------------------------


class TestExtractMusic:
    def test_play_music(self):
        result = {"music": []}
        _extract_music('play music "audio/bgm.ogg"', 5, result)
        assert len(result["music"]) == 1
        assert result["music"][0]["action"] == "play"

    def test_play_sound(self):
        result = {"music": []}
        _extract_music('play sound "sfx/click.wav"', 10, result)
        assert result["music"][0]["action"] == "sound"

    def test_queue(self):
        result = {"music": []}
        _extract_music('queue music "audio/next.ogg"', 15, result)
        assert result["music"][0]["action"] == "queue"

    def test_voice(self):
        result = {"music": []}
        _extract_music('voice "voice/line.ogg"', 20, result)
        assert result["music"][0]["action"] == "voice"

    def test_stop(self):
        result = {"music": []}
        _extract_music("stop music", 25, result)
        assert result["music"][0]["action"] == "stop"

    def test_no_match(self):
        result = {"music": []}
        _extract_music("show eileen happy", 5, result)
        assert len(result["music"]) == 0


# ---------------------------------------------------------------------------
# main() — stdin/stdout JSON protocol (mocked, no SDK)
# ---------------------------------------------------------------------------


def test_main_invalid_json():
    """Invalid JSON on stdin should produce error response."""
    from renpy_analyzer.bridge_worker import main

    with patch("sys.stdin", StringIO("not json")), patch("sys.stdout", new_callable=StringIO) as mock_out:
        main()
        response = json.loads(mock_out.getvalue())
        assert response["success"] is False
        assert len(response["errors"]) == 1
