"""Tests for translation folder case mismatch check."""

import textwrap

from renpy_analyzer.checks.translations import check
from renpy_analyzer.project import load_project


def _project(tmp_path, script_content, tl_dirs=None):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script_content), encoding="utf-8")
    if tl_dirs:
        for d in tl_dirs:
            tl = game / "tl" / d
            tl.mkdir(parents=True, exist_ok=True)
    return load_project(str(tmp_path))


def test_folder_case_mismatch(tmp_path):
    """Translation folder 'Russian' vs block language 'russian' should be flagged."""
    model = _project(
        tmp_path,
        """\
translate russian abc123:
    "Hello" "Привет"
    """,
        tl_dirs=["Russian"],
    )
    findings = check(model)
    case_findings = [f for f in findings if "folder case mismatch" in f.title.lower()]
    assert len(case_findings) == 1
    assert case_findings[0].severity.name == "HIGH"
    assert "Russian" in case_findings[0].description


def test_folder_exact_match_not_flagged(tmp_path):
    """Exact folder name match should not produce findings."""
    model = _project(
        tmp_path,
        """\
translate russian abc123:
    "Hello" "Привет"
    """,
        tl_dirs=["russian"],
    )
    findings = check(model)
    case_findings = [f for f in findings if "folder case mismatch" in f.title.lower()]
    assert len(case_findings) == 0


def test_no_tl_dir_no_crash(tmp_path):
    """No tl/ directory should not crash or produce findings."""
    model = _project(
        tmp_path,
        """\
translate french def456:
    "Hello" "Bonjour"
    """,
    )
    findings = check(model)
    case_findings = [f for f in findings if "folder case mismatch" in f.title.lower()]
    assert len(case_findings) == 0


def test_no_translations_no_crash(tmp_path):
    """No translation blocks should not crash."""
    model = _project(
        tmp_path,
        """\
        label start:
            "Hello"
    """,
        tl_dirs=["russian"],
    )
    findings = check(model)
    assert len(findings) == 0
