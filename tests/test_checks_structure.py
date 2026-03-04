"""Tests for project structure check."""

import textwrap

from renpy_analyzer.checks.structure import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content, filename="script.rpy"):
    game = tmp_path / "game"
    game.mkdir()
    (game / filename).write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_missing_label_start(tmp_path):
    model = _project(
        tmp_path,
        """\
        label intro:
            "Hello"
    """,
    )
    findings = check(model)
    critical = [f for f in findings if "label start" in f.title.lower()]
    assert len(critical) == 1
    assert critical[0].severity.name == "CRITICAL"


def test_label_start_present(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
    """,
    )
    findings = check(model)
    start_findings = [f for f in findings if "label start" in f.title.lower()]
    assert len(start_findings) == 0


def test_reserved_filename_00(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
    """,
        filename="00custom.rpy",
    )
    findings = check(model)
    reserved = [f for f in findings if "Reserved" in f.title]
    assert len(reserved) == 1
    assert "00custom.rpy" in reserved[0].description


def test_normal_filename_not_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
    """,
        filename="chapter01.rpy",
    )
    findings = check(model)
    reserved = [f for f in findings if "Reserved" in f.title]
    assert len(reserved) == 0


def test_empty_project_no_crash(tmp_path):
    """Empty project (no files) should not crash or produce false positives."""
    game = tmp_path / "game"
    game.mkdir()
    model = load_project(str(tmp_path))
    findings = check(model)
    # No files means no label start finding (we check project.files is non-empty)
    assert len(findings) == 0
