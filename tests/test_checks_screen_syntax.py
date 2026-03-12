"""Tests for checks/screen_syntax.py — ternary if and property validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.screen_syntax import check
from renpy_analyzer.models import ProjectModel, Severity
from renpy_analyzer.project import load_project


def _model_with_raw(raw_lines: dict[str, list[str]]) -> ProjectModel:
    model = ProjectModel(root_dir="/test")
    model.raw_lines = raw_lines
    return model


def _project(tmp_path: Path, content: str) -> ProjectModel:
    game = tmp_path / "game"
    game.mkdir()
    (game / "screens.rpy").write_text(textwrap.dedent(content), encoding="utf-8")
    # Need a script.rpy with label start to avoid structure check issues
    (game / "script.rpy").write_text("label start:\n    pass\n", encoding="utf-8")
    return load_project(str(tmp_path))


# --- Ternary if/else detection ---


def test_ternary_if_in_action(tmp_path):
    """action Return(x) if cond else NullAction() should be flagged."""
    model = _project(
        tmp_path,
        """\
        screen map_screen():
            vbox:
                button:
                    action Return(loc_id) if not locked else NullAction()
    """,
    )
    findings = check(model)
    ternary = [f for f in findings if "Ternary" in f.title]
    assert len(ternary) == 1
    assert ternary[0].severity == Severity.CRITICAL


def test_ternary_if_in_sensitive(tmp_path):
    model = _project(
        tmp_path,
        """\
        screen test():
            button:
                sensitive True if unlocked else False
    """,
    )
    findings = check(model)
    ternary = [f for f in findings if "Ternary" in f.title]
    assert len(ternary) == 1


def test_real_if_block_not_flagged(tmp_path):
    """Normal if blocks in screens should not be flagged."""
    model = _project(
        tmp_path,
        """\
        screen test():
            vbox:
                if show_button:
                    textbutton "Click" action NullAction()
    """,
    )
    findings = check(model)
    ternary = [f for f in findings if "Ternary" in f.title]
    assert len(ternary) == 0


def test_if_else_in_string_not_flagged(tmp_path):
    """if/else inside a string literal should not be flagged."""
    model = _project(
        tmp_path,
        """\
        screen test():
            vbox:
                text "Choose if you want to proceed or else go back"
    """,
    )
    findings = check(model)
    ternary = [f for f in findings if "Ternary" in f.title]
    assert len(ternary) == 0


# --- Invalid property detection ---


def test_padding_on_vbox(tmp_path):
    """padding on vbox should be flagged as CRITICAL."""
    model = _project(
        tmp_path,
        """\
        screen test():
            vbox:
                spacing 16
                padding (32, 28)
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 1
    assert invalid[0].severity == Severity.CRITICAL
    assert "padding" in invalid[0].title
    assert "vbox" in invalid[0].title


def test_padding_on_hbox(tmp_path):
    model = _project(
        tmp_path,
        """\
        screen test():
            hbox:
                padding (10, 10)
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 1
    assert "hbox" in invalid[0].title


def test_padding_on_frame_ok(tmp_path):
    """padding on frame is valid and should not be flagged."""
    model = _project(
        tmp_path,
        """\
        screen test():
            frame:
                padding (32, 28)
                text "hello"
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 0


def test_padding_on_button_ok(tmp_path):
    """padding on button is valid and should not be flagged."""
    model = _project(
        tmp_path,
        """\
        screen test():
            button:
                padding (10, 10)
                action NullAction()
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 0


def test_action_on_vbox_flagged(tmp_path):
    """action on vbox should be flagged."""
    model = _project(
        tmp_path,
        """\
        screen test():
            vbox:
                action Return()
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title and "action" in f.title]
    assert len(invalid) == 1


def test_action_on_button_ok(tmp_path):
    """action on button is valid."""
    model = _project(
        tmp_path,
        """\
        screen test():
            button:
                action Return()
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 0


def test_no_findings_outside_screen(tmp_path):
    """Properties outside screen blocks should not be checked."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_nested_statement_tracking(tmp_path):
    """Nested statements should track parent correctly."""
    model = _project(
        tmp_path,
        """\
        screen test():
            frame:
                vbox:
                    padding (10, 10)
    """,
    )
    findings = check(model)
    # padding is on vbox (invalid), not frame
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 1
    assert "vbox" in invalid[0].title


def test_clean_screen_no_findings(tmp_path):
    """A well-formed screen should produce no findings."""
    model = _project(
        tmp_path,
        """\
        screen inventory():
            frame:
                padding (20, 20)
                background "#333"
                vbox:
                    spacing 10
                    text "Items"
                    textbutton "Close" action Return()
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_if_block_does_not_corrupt_parent(tmp_path):
    """Control-flow if/else inside screen should not affect parent tracking."""
    model = _project(
        tmp_path,
        """\
        screen test():
            vbox:
                if show_extra:
                    text "Extra"
                padding (10, 10)
    """,
    )
    findings = check(model)
    # padding is on vbox (if is transparent), should be flagged
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 1
    assert "vbox" in invalid[0].title


def test_for_loop_does_not_corrupt_parent(tmp_path):
    """for loop inside screen should not affect parent tracking."""
    model = _project(
        tmp_path,
        """\
        screen test():
            vbox:
                for item in items:
                    text "[item]"
                padding (10, 10)
    """,
    )
    findings = check(model)
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 1
    assert "vbox" in invalid[0].title


def test_two_screens_in_one_file(tmp_path):
    """Stack should reset between screens in the same file."""
    model = _project(
        tmp_path,
        """\
        screen first():
            frame:
                padding (10, 10)
                text "OK"

        screen second():
            vbox:
                padding (10, 10)
    """,
    )
    findings = check(model)
    # Only vbox padding should be flagged, not frame padding
    invalid = [f for f in findings if "Invalid property" in f.title]
    assert len(invalid) == 1
    assert "vbox" in invalid[0].title


def test_ternary_without_else_not_flagged(tmp_path):
    """sensitive True alone (no else) should NOT be flagged as ternary."""
    model = _project(
        tmp_path,
        """\
        screen test():
            button:
                sensitive True
                action NullAction()
    """,
    )
    findings = check(model)
    ternary = [f for f in findings if "Ternary" in f.title]
    assert len(ternary) == 0
