"""Tests for the CLI interface."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from renpy_analyzer.cli import analyze


def _make_project(tmp_path, script="", renpy_version: str | None = None):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    if renpy_version is not None:
        renpy_dir = game / "renpy"
        renpy_dir.mkdir()
        (renpy_dir / "vc_version.py").write_text(f"version = '{renpy_version}.1234'\n", encoding="utf-8")
    return str(tmp_path)


def _make_sdk(path: Path, version: str = "8.5.2") -> str:
    renpy_dir = path / "renpy"
    renpy_dir.mkdir(parents=True)
    (renpy_dir / "vc_version.py").write_text(f"version = '{version}.1234'\n", encoding="utf-8")
    py_dir = path / "lib" / "py3-linux-x86_64"
    py_dir.mkdir(parents=True)
    (py_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    return str(path)


def test_cli_no_findings_exit_0(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            return
    """,
    )
    result = CliRunner().invoke(analyze, [path])
    assert result.exit_code == 0
    assert "No issues found" in result.output


def test_cli_findings_exit_1(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    result = CliRunner().invoke(analyze, [path])
    assert result.exit_code == 1
    assert "nonexistent" in result.output
    assert "=== Ren'Py Analyzer Results ===" in result.output
    assert "-- CRITICAL" in result.output or "-- HIGH" in result.output


def test_cli_checks_filter(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    # Only run Variables check — should not detect the missing label
    result = CliRunner().invoke(analyze, [path, "--checks", "Variables"])
    assert result.exit_code == 0


def test_cli_unknown_check_exit_2(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n")
    result = CliRunner().invoke(analyze, [path, "--checks", "Bogus"])
    assert result.exit_code == 2
    assert "Unknown" in result.output


def test_cli_json_format(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    result = CliRunner().invoke(analyze, [path, "--format", "json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "severity" in data[0]
    assert "title" in data[0]


def test_cli_pdf_export(tmp_path):
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
    """,
    )
    pdf_path = str(tmp_path / "report.pdf")
    result = CliRunner().invoke(analyze, [path, "--output", pdf_path])
    assert result.exit_code == 1
    assert (tmp_path / "report.pdf").exists()
    # Verify it's a valid PDF (magic bytes)
    with open(pdf_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_cli_text_severity_sections(tmp_path):
    """Severity section headers appear in output."""
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
            $ x = undefined_var
    """,
    )
    result = CliRunner().invoke(analyze, [path])
    assert result.exit_code == 1
    # Should have the results banner and at least one severity section
    assert "=== Ren'Py Analyzer Results ===" in result.output
    assert "unique)" in result.output
    # At least one severity section header present
    has_section = any(
        f"-- {s.name}" in result.output for s in __import__("renpy_analyzer.models", fromlist=["Severity"]).Severity
    )
    assert has_section


def test_cli_text_grouped_findings(tmp_path):
    """Duplicate findings are grouped and show location count."""
    # Two jumps to same nonexistent label → same title, two locations
    path = _make_project(
        tmp_path,
        """\
        label start:
            jump nonexistent
        label other:
            jump nonexistent
    """,
    )
    result = CliRunner().invoke(analyze, [path])
    assert result.exit_code == 1
    # Grouped: should show "locations" for the duplicate finding
    assert "2 locations" in result.output
    assert "unique)" in result.output


def test_cli_sdk_requires_explicit_trust(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n")
    sdk_path = tmp_path / "sdk"
    sdk_path.mkdir()

    result = CliRunner().invoke(analyze, [path, "--sdk-path", str(sdk_path)])

    assert result.exit_code == 2
    assert "--trust-sdk" in result.output


def test_cli_trusted_sdk_is_passed_to_analysis(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n", renpy_version="8.5.2")
    sdk_path = _make_sdk(tmp_path / "sdk", version="8.5.3")

    with patch("renpy_analyzer.cli.run_analysis", return_value=[]) as mock_run_analysis:
        result = CliRunner().invoke(analyze, [path, "--sdk-path", sdk_path, "--trust-sdk"])

    assert result.exit_code == 0
    assert f"Using SDK 8.5.3 at {sdk_path}" in result.output
    assert mock_run_analysis.call_args is not None
    assert mock_run_analysis.call_args.kwargs["sdk_path"] == sdk_path
    assert mock_run_analysis.call_args.kwargs["trust_sdk"] is True


def test_cli_no_matching_sdk_falls_back_to_regex_without_trust(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n", renpy_version="7.4.10")
    sdk_path = _make_sdk(tmp_path / "sdk8", version="8.5.2")

    with patch("renpy_analyzer.cli.run_analysis", return_value=[]) as mock_run_analysis:
        result = CliRunner().invoke(analyze, [path, "--sdk-path", sdk_path])

    assert result.exit_code == 0
    assert "No SDK matches Ren'Py 7.x — using regex parser" in result.output
    assert mock_run_analysis.call_args is not None
    assert mock_run_analysis.call_args.kwargs["sdk_path"] is None
    assert mock_run_analysis.call_args.kwargs["trust_sdk"] is False


def test_cli_rejects_invalid_sdk_when_trusted(tmp_path):
    path = _make_project(tmp_path, "label start:\n    return\n")
    sdk_path = tmp_path / "sdk"
    sdk_path.mkdir()

    result = CliRunner().invoke(analyze, [path, "--sdk-path", str(sdk_path), "--trust-sdk"])

    assert result.exit_code == 2
    assert "Invalid SDK path" in result.output
