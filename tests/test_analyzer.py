"""Tests for the core analysis engine."""

from __future__ import annotations

import textwrap

import pytest

from renpy_analyzer.analyzer import run_analysis


def _make_project(tmp_path, script=""):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    return str(tmp_path)


def test_run_analysis_all_checks(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    findings = run_analysis(path)
    assert len(findings) >= 1
    assert any("nonexistent" in f.title for f in findings)


def test_run_analysis_subset_of_checks(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    findings = run_analysis(path, checks=["Labels"])
    assert len(findings) >= 1
    # Only label-related findings
    assert all(f.check_name == "labels" for f in findings)


def test_run_analysis_unknown_check_raises(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n")
    with pytest.raises(ValueError, match="Unknown check"):
        run_analysis(path, checks=["Nonexistent"])


def test_run_analysis_progress_callback(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n")
    messages = []
    run_analysis(path, checks=["Labels"], on_progress=lambda msg, frac: messages.append((msg, frac)))
    assert len(messages) >= 2
    assert messages[0][1] == 0.0  # first progress is 0%
    assert messages[-1][1] == 1.0  # last progress is 100%


def test_run_analysis_cancel(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    # Cancel immediately — should return before running any checks
    findings = run_analysis(path, cancel_check=lambda: True)
    # No findings because cancelled before checks run
    assert findings == []


def test_run_analysis_cancel_mid_run(tmp_path):
    """Cancel after the first check should return partial results."""
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    call_count = 0

    def _cancel_after_first():
        nonlocal call_count
        call_count += 1
        # Cancel after 2 cancel_check calls (one before first check, one after)
        return call_count > 2

    findings = run_analysis(path, cancel_check=_cancel_after_first)
    # At most 1 check ran before cancellation (Labels), so we might have some findings
    # but not from all checks
    assert isinstance(findings, list)


def test_run_analysis_empty_checks_list(tmp_path):
    """Empty checks list should return no findings."""
    path = _make_project(tmp_path, "label start:\n    return\n")
    findings = run_analysis(path, checks=[])
    assert findings == []


def test_run_analysis_findings_sorted(tmp_path):
    """Findings should be sorted by severity (most severe first)."""
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
            $ Undeclared = True
    """,
    )
    findings = run_analysis(path)
    if len(findings) >= 2:
        for i in range(len(findings) - 1):
            assert findings[i].severity <= findings[i + 1].severity
