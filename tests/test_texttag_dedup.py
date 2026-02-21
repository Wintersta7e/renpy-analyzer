"""Tests for text tag deduplication — duplicate dialogue lines should not produce duplicate findings."""

from renpy_analyzer.checks.texttags import check
from renpy_analyzer.models import DialogueLine, ProjectModel


def _make_project(**kwargs):
    """Create a minimal ProjectModel with the given overrides."""
    return ProjectModel(root_dir="/fake", **kwargs)


def test_duplicate_dialogue_lines_produce_single_set_of_findings():
    """Two DialogueLine entries with the same file+line should be deduplicated."""
    dl1 = DialogueLine(speaker="e", file="script.rpy", line=10, text="{b}hello")
    dl2 = DialogueLine(speaker="e", file="script.rpy", line=10, text="{b}hello")
    project = _make_project(dialogue=[dl1, dl2])

    findings = check(project)

    # {b}hello has one error: unclosed {b}. Without dedup we'd get 2 findings.
    assert len(findings) == 1
    assert "Unclosed" in findings[0].description


def test_different_lines_produce_separate_findings():
    """Two DialogueLine entries with different file+line should yield separate findings."""
    dl1 = DialogueLine(speaker="e", file="script.rpy", line=10, text="{b}hello")
    dl2 = DialogueLine(speaker="e", file="script.rpy", line=20, text="{b}hello")
    project = _make_project(dialogue=[dl1, dl2])

    findings = check(project)

    # Each line produces 1 finding (unclosed {b}), so 2 total
    assert len(findings) == 2


def test_different_files_produce_separate_findings():
    """Two DialogueLine entries in different files but same line number should yield 2 findings."""
    dl1 = DialogueLine(speaker="e", file="a.rpy", line=10, text="{b}oops")
    dl2 = DialogueLine(speaker="e", file="b.rpy", line=10, text="{b}oops")
    project = _make_project(dialogue=[dl1, dl2])

    findings = check(project)

    assert len(findings) == 2


def test_no_duplicates_with_clean_text():
    """Duplicate dialogue lines with valid tags should produce zero findings."""
    dl1 = DialogueLine(speaker="e", file="script.rpy", line=5, text="{i}hello{/i}")
    dl2 = DialogueLine(speaker="e", file="script.rpy", line=5, text="{i}hello{/i}")
    project = _make_project(dialogue=[dl1, dl2])

    findings = check(project)

    assert len(findings) == 0
