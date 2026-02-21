"""Tests for nested menu parsing."""

import textwrap
from pathlib import Path

from renpy_analyzer.parser import parse_file


def _write_rpy(tmp_path: Path, content: str) -> str:
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


def test_simple_non_nested_menu(tmp_path):
    """A simple (non-nested) menu with two choices should still work correctly."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            menu:
                "Go left":
                    mc "I'll go left."
                    jump left_path
                "Go right":
                    mc "I'll go right."
                    mc "This way looks good."
        label left_path:
            return
    """,
    )
    result = parse_file(path)
    assert len(result["menus"]) == 1
    menu = result["menus"][0]
    assert len(menu.choices) == 2

    assert menu.choices[0].text == "Go left"
    assert menu.choices[0].content_lines == 2
    assert menu.choices[0].has_jump is True

    assert menu.choices[1].text == "Go right"
    assert menu.choices[1].content_lines == 2
    assert menu.choices[1].has_jump is False


def test_nested_menu(tmp_path):
    """A nested menu inside a choice should produce two separate Menu objects."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            menu:
                "Check Chloe's room":
                    p "Hey Rose!"
                    r "Oh hey!"
                    menu:
                        "I miss her":
                            p "I miss her..."
                        "I can survive":
                            p "I can survive"
                    scene 1cdri3
                "Go outside":
                    p "Let's go."
        label ending:
            return
    """,
    )
    result = parse_file(path)

    # Two separate Menu objects should be produced
    assert len(result["menus"]) == 2

    # Find inner and outer menus by their line numbers
    # The outer menu is declared first (earlier line)
    menus_sorted = sorted(result["menus"], key=lambda m: m.line)
    outer_menu = menus_sorted[0]
    inner_menu = menus_sorted[1]

    # --- Outer menu ---
    assert len(outer_menu.choices) == 2
    assert outer_menu.choices[0].text == "Check Chloe's room"
    # The outer choice has content: 2 dialogue lines + menu: line counted as content +
    # 1 for the nested menu block (pop increment) + 1 for "scene 1cdri3"
    assert outer_menu.choices[0].content_lines > 0
    assert outer_menu.choices[1].text == "Go outside"
    assert outer_menu.choices[1].content_lines > 0

    # --- Inner menu ---
    assert len(inner_menu.choices) == 2
    assert inner_menu.choices[0].text == "I miss her"
    assert inner_menu.choices[0].content_lines == 1  # p "I miss her..."
    assert inner_menu.choices[1].text == "I can survive"
    assert inner_menu.choices[1].content_lines == 1  # p "I can survive"


def test_double_nested_menu(tmp_path):
    """Three levels of nested menus should all produce separate Menu objects."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            menu:
                "Level 1 choice A":
                    p "Entering level 1A"
                    menu:
                        "Level 2 choice A":
                            p "Entering level 2A"
                            menu:
                                "Level 3 choice A":
                                    p "Deep inside"
                                "Level 3 choice B":
                                    p "Also deep"
                            p "Back in level 2A"
                        "Level 2 choice B":
                            p "Level 2B content"
                    p "Back in level 1A"
                "Level 1 choice B":
                    p "Level 1B content"
        label ending:
            return
    """,
    )
    result = parse_file(path)

    # Three separate Menu objects (one per nesting level)
    assert len(result["menus"]) == 3

    menus_sorted = sorted(result["menus"], key=lambda m: m.line)
    level1 = menus_sorted[0]
    level2 = menus_sorted[1]
    level3 = menus_sorted[2]

    # Level 1: 2 choices
    assert len(level1.choices) == 2
    assert level1.choices[0].text == "Level 1 choice A"
    assert level1.choices[0].content_lines > 0
    assert level1.choices[1].text == "Level 1 choice B"
    assert level1.choices[1].content_lines > 0

    # Level 2: 2 choices
    assert len(level2.choices) == 2
    assert level2.choices[0].text == "Level 2 choice A"
    assert level2.choices[0].content_lines > 0
    assert level2.choices[1].text == "Level 2 choice B"
    assert level2.choices[1].content_lines > 0

    # Level 3: 2 choices
    assert len(level3.choices) == 2
    assert level3.choices[0].text == "Level 3 choice A"
    assert level3.choices[0].content_lines == 1
    assert level3.choices[1].text == "Level 3 choice B"
    assert level3.choices[1].content_lines == 1


def test_nested_menu_at_end_of_file(tmp_path):
    """Nested menus at end of file (no dedent) should all be finalized correctly."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            menu:
                "Outer choice":
                    menu:
                        "Inner choice A":
                            p "Content A"
                        "Inner choice B":
                            p "Content B"
    """,
    )
    result = parse_file(path)

    # Both menus should be captured even at EOF
    assert len(result["menus"]) == 2

    menus_sorted = sorted(result["menus"], key=lambda m: m.line)
    outer = menus_sorted[0]
    inner = menus_sorted[1]

    assert len(outer.choices) == 1
    assert outer.choices[0].text == "Outer choice"
    assert outer.choices[0].content_lines > 0

    assert len(inner.choices) == 2
    assert inner.choices[0].text == "Inner choice A"
    assert inner.choices[0].content_lines == 1
    assert inner.choices[1].text == "Inner choice B"
    assert inner.choices[1].content_lines == 1


def test_nested_menu_inner_choices_not_in_outer(tmp_path):
    """Inner menu choices must NOT appear in the outer menu's choice list."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            menu:
                "Outer A":
                    menu:
                        "Inner X":
                            p "X content"
                        "Inner Y":
                            p "Y content"
                "Outer B":
                    p "B content"
        label ending:
            return
    """,
    )
    result = parse_file(path)

    assert len(result["menus"]) == 2
    menus_sorted = sorted(result["menus"], key=lambda m: m.line)
    outer = menus_sorted[0]
    inner = menus_sorted[1]

    # Outer menu should only have "Outer A" and "Outer B"
    outer_texts = [c.text for c in outer.choices]
    assert outer_texts == ["Outer A", "Outer B"]

    # Inner menu should only have "Inner X" and "Inner Y"
    inner_texts = [c.text for c in inner.choices]
    assert inner_texts == ["Inner X", "Inner Y"]


def test_sequential_menus_not_confused_with_nesting(tmp_path):
    """Two sequential (non-nested) menus at the same indent should be separate."""
    path = _write_rpy(
        tmp_path,
        """\
        label start:
            menu:
                "First A":
                    p "Content A"
                "First B":
                    p "Content B"
            menu:
                "Second A":
                    p "Content A2"
                "Second B":
                    p "Content B2"
        label ending:
            return
    """,
    )
    result = parse_file(path)

    assert len(result["menus"]) == 2
    menus_sorted = sorted(result["menus"], key=lambda m: m.line)

    assert len(menus_sorted[0].choices) == 2
    assert menus_sorted[0].choices[0].text == "First A"
    assert menus_sorted[0].choices[1].text == "First B"

    assert len(menus_sorted[1].choices) == 2
    assert menus_sorted[1].choices[0].text == "Second A"
    assert menus_sorted[1].choices[1].text == "Second B"
