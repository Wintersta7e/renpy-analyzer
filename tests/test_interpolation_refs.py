"""Tests for screen text interpolation [var] and ShowMenu screen ref tracking."""

import textwrap
from pathlib import Path

from renpy_analyzer.checks.screens import check as screens_check
from renpy_analyzer.checks.variables import check as variables_check
from renpy_analyzer.models import Severity
from renpy_analyzer.project import load_project


def _project(tmp_path: Path, *files: tuple[str, str]):
    game = tmp_path / "game"
    game.mkdir()
    for name, content in files:
        (game / name).write_text(textwrap.dedent(content), encoding="utf-8")
    return load_project(str(tmp_path))


# --- Variable interpolation [var] tracking ---


def test_interpolation_in_screen_text_not_unused(tmp_path):
    """Variables used in screen text via [var] should not be flagged as unused."""
    model = _project(
        tmp_path,
        (
            "variables.rpy",
            """\
            default money = 100
            default day = 1
        """,
        ),
        (
            "screens.rpy",
            """\
            screen hud():
                text "[money] gold"
                text "Day [day]"
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Hello"
        """,
        ),
    )
    findings = variables_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    unused_names = {f.title.split("'")[1] for f in unused}
    assert "money" not in unused_names
    assert "day" not in unused_names


def test_interpolation_in_dialogue_not_unused(tmp_path):
    """Variables used in dialogue via [var] should not be flagged as unused."""
    model = _project(
        tmp_path,
        (
            "variables.rpy",
            """\
            default player_name = "Player"
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Hello, [player_name]!"
        """,
        ),
    )
    findings = variables_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    unused_names = {f.title.split("'")[1] for f in unused}
    assert "player_name" not in unused_names


def test_unrelated_brackets_dont_create_refs(tmp_path):
    """Square brackets in non-interpolation context shouldn't create false refs."""
    model = _project(
        tmp_path,
        (
            "variables.rpy",
            """\
            default truly_unused = 0
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Hello"
        """,
        ),
    )
    findings = variables_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert any("truly_unused" in f.title for f in unused)


# --- ShowMenu / Show screen reference tracking ---


def test_showmenu_counts_as_screen_ref(tmp_path):
    """ShowMenu("name") in an action should count as a screen reference."""
    model = _project(
        tmp_path,
        (
            "screens.rpy",
            """\
            screen stats():
                text "Stats"

            screen hud():
                textbutton "Stats" action ShowMenu("stats")
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Hello"
        """,
        ),
    )
    findings = screens_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    unused_names = {f.title.split("'")[1] for f in unused}
    assert "stats" not in unused_names


def test_toggle_screen_counts_as_screen_ref(tmp_path):
    """ToggleScreen("name") in an action should count as a screen reference."""
    model = _project(
        tmp_path,
        (
            "screens.rpy",
            """\
            screen overlay():
                text "Overlay"

            screen hud():
                textbutton "Toggle" action ToggleScreen("overlay")
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Hello"
        """,
        ),
    )
    findings = screens_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    unused_names = {f.title.split("'")[1] for f in unused}
    assert "overlay" not in unused_names


def test_hide_action_counts_as_screen_ref(tmp_path):
    """Hide("name") in an action should count as a screen reference."""
    model = _project(
        tmp_path,
        (
            "screens.rpy",
            """\
            screen notification():
                text "Notice"

            screen hud():
                textbutton "Dismiss" action Hide("notification")
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Hello"
        """,
        ),
    )
    findings = screens_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    unused_names = {f.title.split("'")[1] for f in unused}
    assert "notification" not in unused_names


def test_renpy_show_screen_counts_as_ref(tmp_path):
    """renpy.show_screen("name") should count as a screen reference."""
    model = _project(
        tmp_path,
        (
            "screens.rpy",
            """\
            screen dialog():
                text "Dialog"
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                $ renpy.show_screen("dialog")
        """,
        ),
    )
    findings = screens_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    unused_names = {f.title.split("'")[1] for f in unused}
    assert "dialog" not in unused_names


# --- Undeclared variable severity ---


def test_dollar_assign_undeclared_is_style(tmp_path):
    """$ var = ... without default should be STYLE, not MEDIUM."""
    model = _project(
        tmp_path,
        (
            "script.rpy",
            """\
            label start:
                $ temp_var = 42
        """,
        ),
    )
    findings = variables_check(model)
    undecl = [f for f in findings if "Undeclared" in f.title and "temp_var" in f.title]
    assert len(undecl) == 1
    assert undecl[0].severity == Severity.STYLE


def test_escaped_bracket_not_counted_as_ref(tmp_path):
    """[[var] (escaped bracket) should NOT count as a variable reference."""
    model = _project(
        tmp_path,
        (
            "variables.rpy",
            """\
            default escaped_var = 0
        """,
        ),
        (
            "script.rpy",
            """\
            label start:
                "Use [[escaped_var] to show brackets"
        """,
        ),
    )
    findings = variables_check(model)
    unused = [f for f in findings if "Unused" in f.title]
    assert any("escaped_var" in f.title for f in unused)


def test_undeclared_dedup(tmp_path):
    """Multiple $ assignments of the same undeclared var should produce one finding."""
    model = _project(
        tmp_path,
        (
            "script.rpy",
            """\
            label start:
                $ temp = 1
                $ temp = 2
                $ temp = 3
        """,
        ),
    )
    findings = variables_check(model)
    undecl = [f for f in findings if "Undeclared" in f.title and "temp" in f.title]
    assert len(undecl) == 1
