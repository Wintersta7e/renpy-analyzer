"""Tests for persistent variable initialization check."""

import textwrap

from renpy_analyzer.checks.persistent import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_declared_persistent_used_in_condition(tmp_path):
    """persistent.x with default, used in condition — no finding."""
    model = _project(tmp_path, """\
        default persistent.unlocked = False

        label start:
            if persistent.unlocked:
                "You unlocked it!"
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_undeclared_persistent_in_condition(tmp_path):
    """persistent.x in condition without default — HIGH finding."""
    model = _project(tmp_path, """\
        label start:
            if persistent.beaten:
                "You beat the game!"
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity.name == "HIGH"
    assert "persistent.beaten" in findings[0].title
    assert findings[0].check_name == "persistent"


def test_write_only_no_finding(tmp_path):
    """persistent.x only assigned (not read) — no finding."""
    model = _project(tmp_path, """\
        label start:
            $ persistent.score = 100
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_augmented_assign_without_default(tmp_path):
    """persistent.x += 1 without default — HIGH finding (reads current value)."""
    model = _project(tmp_path, """\
        label start:
            $ persistent.count += 1
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert "persistent.count" in findings[0].title


def test_define_persistent_not_flagged(tmp_path):
    """define persistent.x — wrong keyword, but NOT flagged by THIS check (handled by variables check)."""
    model = _project(tmp_path, """\
        define persistent.setting = True

        label start:
            if persistent.setting:
                "On"
            return
    """)
    findings = check(model)
    # 'define' is NOT 'default', so persistent.setting is not declared.
    # The condition reference should be flagged.
    assert len(findings) == 1
    assert "persistent.setting" in findings[0].title


def test_multiple_refs_deduplicated(tmp_path):
    """Multiple references to same uninitialized persistent — one finding."""
    model = _project(tmp_path, """\
        label start:
            if persistent.flag:
                "A"
            if persistent.flag:
                "B"
            return
    """)
    findings = check(model)
    assert len(findings) == 1


def test_declared_persistent_with_augment(tmp_path):
    """persistent.x with default AND augment — no finding."""
    model = _project(tmp_path, """\
        default persistent.plays = 0

        label start:
            $ persistent.plays += 1
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_underscore_prefixed_skipped(tmp_path):
    """persistent._internal vars are engine internals — not flagged."""
    model = _project(tmp_path, """\
        label start:
            if persistent._file_page:
                "Page set"
            if persistent._achievements:
                "Has achievements"
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_underscore_prefixed_augment_skipped(tmp_path):
    """persistent._internal augmented assign — not flagged."""
    model = _project(tmp_path, """\
        label start:
            $ persistent._visit_count += 1
            return
    """)
    findings = check(model)
    assert len(findings) == 0


def test_non_underscore_still_flagged(tmp_path):
    """persistent.user_var (no underscore prefix) without default — still flagged."""
    model = _project(tmp_path, """\
        label start:
            if persistent.beaten_game:
                "You won!"
            return
    """)
    findings = check(model)
    assert len(findings) == 1
    assert "persistent.beaten_game" in findings[0].title


def test_empty_model(tmp_path):
    from renpy_analyzer.models import ProjectModel
    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []
