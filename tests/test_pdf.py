"""Tests for PDF report generation."""

from __future__ import annotations

from pathlib import Path

from renpy_analyzer.models import Finding, Severity
from renpy_analyzer.report.pdf import generate_pdf


def _finding(
    severity=Severity.HIGH,
    check_name="labels",
    title="Test finding",
    description="A test finding description.",
    file="script.rpy",
    line=1,
    suggestion="",
) -> Finding:
    return Finding(
        severity=severity,
        check_name=check_name,
        title=title,
        description=description,
        file=file,
        line=line,
        suggestion=suggestion,
    )


def test_pdf_zero_findings(tmp_path):
    """PDF generation with 0 findings should produce a valid PDF."""
    out = str(tmp_path / "report.pdf")
    generate_pdf([], out, game_name="TestGame", game_path="/tmp/test")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 500  # non-trivial content


def test_pdf_single_finding(tmp_path):
    out = str(tmp_path / "report.pdf")
    findings = [_finding()]
    generate_pdf(findings, out, game_name="TestGame")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"


def test_pdf_all_severities(tmp_path):
    """PDF should handle findings across all severity levels."""
    out = str(tmp_path / "report.pdf")
    findings = [
        _finding(severity=Severity.CRITICAL, check_name="labels", title="Critical issue"),
        _finding(severity=Severity.HIGH, check_name="variables", title="High issue"),
        _finding(severity=Severity.MEDIUM, check_name="logic", title="Medium issue"),
        _finding(severity=Severity.LOW, check_name="characters", title="Low issue"),
        _finding(severity=Severity.STYLE, check_name="logic", title="Style issue"),
    ]
    generate_pdf(findings, out, game_name="Multi-Severity Game")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 2000


def test_pdf_duplicate_titles_grouped(tmp_path):
    """Findings with identical titles should be grouped in the PDF."""
    out = str(tmp_path / "report.pdf")
    findings = [
        _finding(title="Missing label 'x'", file="a.rpy", line=10),
        _finding(title="Missing label 'x'", file="b.rpy", line=20),
        _finding(title="Missing label 'x'", file="c.rpy", line=30),
    ]
    generate_pdf(findings, out, game_name="Grouped Test")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"


def test_pdf_unicode_content(tmp_path):
    """PDF should handle unicode characters in findings without crashing."""
    out = str(tmp_path / "report.pdf")
    findings = [
        _finding(
            title="Undefined speaker '\u65e5\u672c\u8a9e'",
            description="Speaker '\u65e5\u672c\u8a9e' used at script.rpy:5.",
            suggestion="Add 'define \u65e5\u672c\u8a9e = Character(\"Name\")'.",
        ),
    ]
    generate_pdf(findings, out, game_name="Unicode \u30c6\u30b9\u30c8")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"


def test_pdf_long_description(tmp_path):
    """PDF should handle very long finding descriptions without crashing."""
    out = str(tmp_path / "report.pdf")
    findings = [
        _finding(
            title="A" * 200,
            description="B " * 500,
            suggestion="C " * 300,
        ),
    ]
    generate_pdf(findings, out, game_name="Long Content Test")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"


def test_pdf_all_categories(tmp_path):
    """PDF should render sections for all 7 check categories."""
    out = str(tmp_path / "report.pdf")
    findings = [
        _finding(severity=Severity.CRITICAL, check_name="labels", title="Label issue"),
        _finding(severity=Severity.HIGH, check_name="variables", title="Var issue"),
        _finding(severity=Severity.CRITICAL, check_name="logic", title="Logic issue"),
        _finding(severity=Severity.HIGH, check_name="menus", title="Menu issue"),
        _finding(severity=Severity.MEDIUM, check_name="assets", title="Asset issue"),
        _finding(severity=Severity.LOW, check_name="characters", title="Char issue"),
        _finding(severity=Severity.HIGH, check_name="flow", title="Flow issue"),
    ]
    generate_pdf(findings, out, game_name="All Categories")
    data = Path(out).read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 5000
