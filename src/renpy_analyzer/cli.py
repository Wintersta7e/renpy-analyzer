"""Command-line interface for Ren'Py Analyzer."""

from __future__ import annotations

import json
import sys

import click

from .analyzer import run_analysis
from .checks import ALL_CHECKS
from .log import setup_logging
from .models import Severity

SEVERITY_COLORS: dict[Severity, str] = {
    Severity.CRITICAL: "red",
    Severity.HIGH: "yellow",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "green",
    Severity.STYLE: "cyan",
}


@click.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option(
    "--checks", "check_names", default=None,
    help=f"Comma-separated check names (default: all). Available: {', '.join(ALL_CHECKS)}",
)
@click.option("--output", "-o", default=None, type=click.Path(), help="Export PDF report to this path.")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.option(
    "--format", "fmt", type=click.Choice(["text", "json"]), default="text",
    help="Output format (default: text).",
)
@click.option(
    "--sdk-path", default=None, type=click.Path(exists=True),
    help="Path to a Ren'Py SDK directory. Uses SDK's parser instead of regex.",
)
def analyze(project_path: str, check_names: str | None, output: str | None, verbose: bool, fmt: str, sdk_path: str | None) -> None:
    """Analyze a Ren'Py project for bugs and issues."""
    setup_logging(verbose=verbose)

    checks = None
    if check_names:
        checks = [c.strip() for c in check_names.split(",")]

    try:
        findings = run_analysis(
            project_path,
            checks=checks,
            on_progress=lambda msg, _frac: (click.echo(msg, err=True) if verbose else None),
            sdk_path=sdk_path,
        )
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)
    except RuntimeError as exc:
        click.echo(f"SDK error: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if fmt == "json":
        _output_json(findings)
    else:
        _output_text(findings)

    if output:
        _export_pdf(findings, output, project_path)

    sys.exit(1 if findings else 0)


def _output_text(findings: list) -> None:
    if not findings:
        click.echo("No issues found.")
        return

    for finding in findings:
        sev = finding.severity
        badge = click.style(f"[{sev.name}]", fg=SEVERITY_COLORS[sev], bold=True)
        click.echo(f"{badge} {finding.title}")
        click.echo(f"  {finding.file}:{finding.line}")
        if finding.description:
            click.echo(f"  {finding.description}")
        if finding.suggestion:
            click.echo(click.style(f"  -> {finding.suggestion}", fg="green"))
        click.echo()

    click.echo(f"Total: {len(findings)} finding(s).", err=True)


def _output_json(findings: list) -> None:
    data = [
        {
            "severity": f.severity.name,
            "check": f.check_name,
            "title": f.title,
            "file": f.file,
            "line": f.line,
            "description": f.description,
            "suggestion": f.suggestion,
        }
        for f in findings
    ]
    click.echo(json.dumps(data, indent=2))


def _export_pdf(findings: list, output_path: str, project_path: str) -> None:
    from pathlib import Path

    from .report.pdf import generate_pdf

    game_name = Path(project_path).name
    generate_pdf(
        findings=findings,
        output_path=output_path,
        game_name=game_name,
        game_path=project_path,
    )
    click.echo(f"PDF report saved to {output_path}", err=True)
