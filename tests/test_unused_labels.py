"""Tests for unused labels check."""

import textwrap

from renpy_analyzer.checks.labels import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_unused_label_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"

        label orphan:
            "Nobody jumps here"
    """,
    )
    findings = check(model)
    unused = [f for f in findings if "Unused label" in f.title]
    assert len(unused) == 1
    assert "orphan" in unused[0].title
    assert unused[0].severity.name == "LOW"


def test_used_label_not_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            jump chapter1

        label chapter1:
            "In chapter 1"
    """,
    )
    findings = check(model)
    unused = [f for f in findings if "Unused label" in f.title]
    assert len(unused) == 0


def test_engine_labels_not_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"

        label after_load:
            return

        label splashscreen:
            return

        label quit:
            return
    """,
    )
    findings = check(model)
    unused = [f for f in findings if "Unused label" in f.title]
    assert len(unused) == 0


def test_called_label_not_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            call helper
            "Done"

        label helper:
            "Helping"
            return
    """,
    )
    findings = check(model)
    unused = [f for f in findings if "Unused label" in f.title]
    assert len(unused) == 0


def test_dynamic_jumps_skip_unused_check(tmp_path):
    """When dynamic jumps exist, unused label check is skipped entirely."""
    model = _project(
        tmp_path,
        """\
        label start:
            jump expression "chapter_" + str(chapter)

        label chapter_1:
            "Chapter 1"
    """,
    )
    findings = check(model)
    unused = [f for f in findings if "Unused label" in f.title]
    assert len(unused) == 0
