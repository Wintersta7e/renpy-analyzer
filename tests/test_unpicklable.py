"""Tests for non-serializable store variable check."""

import textwrap

from renpy_analyzer.checks.variables import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    return load_project(str(tmp_path))


def test_lambda_in_store_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            $ my_func = lambda x: x + 1
    """,
    )
    findings = check(model)
    unpick = [f for f in findings if "serializable" in f.title.lower()]
    assert len(unpick) == 1
    assert unpick[0].severity.name == "HIGH"
    assert "my_func" in unpick[0].title


def test_open_in_store_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            $ logfile = open("game.log", "w")
    """,
    )
    findings = check(model)
    unpick = [f for f in findings if "serializable" in f.title.lower()]
    assert len(unpick) == 1
    assert "logfile" in unpick[0].title


def test_default_lambda_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        default sorter = lambda x: x.name
    """,
    )
    findings = check(model)
    unpick = [f for f in findings if "serializable" in f.title.lower()]
    assert len(unpick) == 1


def test_normal_assignment_not_flagged(tmp_path):
    model = _project(
        tmp_path,
        """\
        label start:
            $ score = 10
            $ name = "Player"
    """,
    )
    findings = check(model)
    unpick = [f for f in findings if "serializable" in f.title.lower()]
    assert len(unpick) == 0


def test_define_lambda_not_flagged(tmp_path):
    """define variables are not saved, so lambda is fine there."""
    model = _project(
        tmp_path,
        """\
        define my_func = lambda x: x + 1
    """,
    )
    findings = check(model)
    unpick = [f for f in findings if "serializable" in f.title.lower()]
    assert len(unpick) == 0
