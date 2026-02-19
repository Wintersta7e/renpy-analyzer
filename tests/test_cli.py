"""Tests for the CLI interface."""

from __future__ import annotations

import json
import textwrap

from click.testing import CliRunner

from renpy_analyzer.cli import analyze


def _make_project(tmp_path, script=""):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    return str(tmp_path)


def test_cli_no_findings_exit_0(tmp_path):
    path = _make_project(tmp_path, """\
        label start:
            return
    """)
    result = CliRunner().invoke(analyze, [path])
    assert result.exit_code == 0
    assert "No issues found" in result.output


def test_cli_findings_exit_1(tmp_path):
    path = _make_project(tmp_path, """\
        label start:
            jump nonexistent
    """)
    result = CliRunner().invoke(analyze, [path])
    assert result.exit_code == 1
    assert "nonexistent" in result.output


def test_cli_checks_filter(tmp_path):
    path = _make_project(tmp_path, """\
        label start:
            jump nonexistent
    """)
    # Only run Variables check — should not detect the missing label
    result = CliRunner().invoke(analyze, [path, "--checks", "Variables"])
    assert result.exit_code == 0


def test_cli_unknown_check_exit_2(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n")
    result = CliRunner().invoke(analyze, [path, "--checks", "Bogus"])
    assert result.exit_code == 2
    assert "Unknown" in result.output


def test_cli_json_format(tmp_path):
    path = _make_project(tmp_path, """\
        label start:
            jump nonexistent
    """)
    result = CliRunner().invoke(analyze, [path, "--format", "json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "severity" in data[0]
    assert "title" in data[0]


def test_cli_pdf_export(tmp_path):
    path = _make_project(tmp_path, """\
        label start:
            jump nonexistent
    """)
    pdf_path = str(tmp_path / "report.pdf")
    result = CliRunner().invoke(analyze, [path, "--output", pdf_path])
    assert result.exit_code == 1
    assert (tmp_path / "report.pdf").exists()
    # Verify it's a valid PDF (magic bytes)
    with open(pdf_path, "rb") as f:
        assert f.read(5) == b"%PDF-"
