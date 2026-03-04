"""Tests for NVL overflow check."""

import textwrap

from renpy_analyzer.checks.nvl import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def _make_nvl_lines(speaker, count):
    """Generate `count` NVL dialogue lines."""
    return "\n".join(f'    {speaker} "Line {i+1}"' for i in range(count))


def test_nvl_overflow_flagged(tmp_path):
    """15+ NVL lines without clear should be flagged."""
    lines = _make_nvl_lines("narrator_nvl", 16)
    model = _project(
        tmp_path,
        f"""\
define narrator_nvl = Character(None, kind=nvl)

label start:
{lines}
""",
    )
    findings = check(model)
    overflow = [f for f in findings if "NVL overflow" in f.title]
    assert len(overflow) == 1
    assert overflow[0].severity.name == "MEDIUM"


def test_nvl_with_clear_not_flagged(tmp_path):
    """NVL lines with periodic clears should not be flagged."""
    model = _project(
        tmp_path,
        """\
define narrator_nvl = Character(None, kind=nvl)

label start:
    narrator_nvl "Line 1"
    narrator_nvl "Line 2"
    narrator_nvl "Line 3"
    nvl clear
    narrator_nvl "Line 4"
    narrator_nvl "Line 5"
""",
    )
    findings = check(model)
    overflow = [f for f in findings if "NVL overflow" in f.title]
    assert len(overflow) == 0


def test_no_nvl_characters(tmp_path):
    """No NVL characters should produce no findings."""
    model = _project(
        tmp_path,
        """\
define mc = Character("Player")

label start:
    mc "Hello"
""",
    )
    findings = check(model)
    assert len(findings) == 0


def test_scene_resets_nvl_counter(tmp_path):
    """Scene change should reset the NVL line counter."""
    lines_a = _make_nvl_lines("narrator_nvl", 10)
    lines_b = _make_nvl_lines("narrator_nvl", 10)
    model = _project(
        tmp_path,
        f"""\
define narrator_nvl = Character(None, kind=nvl)

label start:
{lines_a}
    scene bg_room
{lines_b}
""",
    )
    findings = check(model)
    overflow = [f for f in findings if "NVL overflow" in f.title]
    assert len(overflow) == 0


def test_under_threshold_not_flagged(tmp_path):
    """Lines under the threshold should not be flagged."""
    lines = _make_nvl_lines("narrator_nvl", 14)
    model = _project(
        tmp_path,
        f"""\
define narrator_nvl = Character(None, kind=nvl)

label start:
{lines}
""",
    )
    findings = check(model)
    overflow = [f for f in findings if "NVL overflow" in f.title]
    assert len(overflow) == 0
