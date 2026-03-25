"""Tests for call-prerequisite check (@requires annotation)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.callprereqs import check
from renpy_analyzer.models import ProjectModel, Severity
from renpy_analyzer.project import load_project


def _project(tmp_path: Path, content: str) -> ProjectModel:
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_requires_satisfied(tmp_path):
    """All required vars assigned before call — no finding."""
    model = _project(
        tmp_path,
        """\
        # @requires: _target
        label helper:
            $ result = _target + 1
            return

        label start:
            $ _target = 5
            call helper
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_requires_missing(tmp_path):
    """Required var not assigned before call — HIGH finding."""
    model = _project(
        tmp_path,
        """\
        # @requires: _target
        label helper:
            $ result = _target + 1
            return

        label start:
            call helper
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "_target" in findings[0].description
    assert "helper" in findings[0].title


def test_requires_partial(tmp_path):
    """One of two required vars missing — finding for the missing one."""
    model = _project(
        tmp_path,
        """\
        # @requires: _char, _queue
        label sms_exchange:
            return

        label start:
            $ _char = "Alice"
            call sms_exchange
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 1
    assert "_queue" in findings[0].description
    assert "_char" not in findings[0].description


def test_requires_multiple_calls(tmp_path):
    """Two calls to same label — both checked independently."""
    model = _project(
        tmp_path,
        """\
        # @requires: _x
        label helper:
            return

        label start:
            call helper
            $ _x = 1
            call helper
            return
    """,
    )
    findings = check(model)
    # First call missing _x, second call has it
    assert len(findings) == 1


def test_requires_no_annotation(tmp_path):
    """Label without @requires — call is fine regardless."""
    model = _project(
        tmp_path,
        """\
        label helper:
            return

        label start:
            call helper
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_requires_call_to_missing_label(tmp_path):
    """Call to undefined label with @requires — skip (labels check handles it)."""
    model = _project(
        tmp_path,
        """\
        label start:
            call nonexistent
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_requires_default_does_not_satisfy(tmp_path):
    """A top-level 'default' should NOT satisfy @requires (it's set-if-unset)."""
    model = _project(
        tmp_path,
        """\
        default _target = 0

        # @requires: _target
        label helper:
            return

        label start:
            call helper
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 1


def test_requires_augmented_assign_satisfies(tmp_path):
    """Augmented assignment ($ _x += 1) should satisfy @requires."""
    model = _project(
        tmp_path,
        """\
        # @requires: _x
        label helper:
            return

        label start:
            $ _x += 1
            call helper
            return
    """,
    )
    findings = check(model)
    assert len(findings) == 0


def test_requires_blank_line_between_comment_and_label(tmp_path):
    """@requires comment must be immediately above the label (no blank lines)."""
    model = _project(
        tmp_path,
        """\
        # @requires: _x

        label helper:
            return

        label start:
            call helper
            return
    """,
    )
    # Blank line breaks the association — no requirements registered
    findings = check(model)
    assert len(findings) == 0


def test_empty_model():
    """Empty project produces no findings."""
    model = ProjectModel(root_dir="/test")
    findings = check(model)
    assert findings == []
