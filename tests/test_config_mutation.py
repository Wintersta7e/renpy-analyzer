"""Tests for config runtime mutation check."""

import textwrap

from renpy_analyzer.checks.variables import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_config_mutation_at_runtime(tmp_path):
    """config.* modified inside a label (not init) should be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            $ config.rollback_enabled = False
    """,
    )
    findings = check(model)
    config_findings = [f for f in findings if "config" in f.title.lower() and "runtime" in f.title.lower()]
    assert len(config_findings) == 1
    assert config_findings[0].severity.name == "MEDIUM"


def test_config_in_init_not_flagged(tmp_path):
    """config.* default inside init: block should NOT be flagged."""
    model = _project(
        tmp_path,
        """\
init:
    default config.rollback_enabled = False
    """,
    )
    findings = check(model)
    config_findings = [f for f in findings if "config" in f.title.lower() and "runtime" in f.title.lower()]
    assert len(config_findings) == 0


def test_config_in_init_python_not_captured(tmp_path):
    """config.* inside init python (plain Python, no $) isn't captured by parser.

    This is expected — our regex parser only captures $ assignments, not plain Python.
    """
    model = _project(
        tmp_path,
        """\
init python:
    config.rollback_enabled = False
    """,
    )
    findings = check(model)
    # No config findings because the parser doesn't capture plain Python assignments
    config_findings = [f for f in findings if "config" in f.title.lower() and "runtime" in f.title.lower()]
    assert len(config_findings) == 0


def test_config_augment_at_runtime(tmp_path):
    """config.* augmented (+=) at runtime should be flagged."""
    model = _project(
        tmp_path,
        """\
        label start:
            $ config.overlay_screens += ["custom"]
    """,
    )
    findings = check(model)
    config_findings = [f for f in findings if "config" in f.title.lower() and "runtime" in f.title.lower()]
    assert len(config_findings) == 1
