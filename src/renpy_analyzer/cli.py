"""Command-line interface for Ren'Py Analyzer."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field

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

_MAX_LOCATIONS_SHOWN = 5


@dataclass
class _GroupedFinding:
    severity: Severity
    check_name: str
    title: str
    locations: list[tuple[str, int]] = field(default_factory=list)


def _group_findings(findings: list) -> dict[Severity, list[_GroupedFinding]]:
    """Group findings by (severity, check_name, title), collecting locations."""
    key_map: dict[tuple, _GroupedFinding] = {}
    order: dict[tuple, int] = {}
    for f in findings:
        key = (f.severity, f.check_name, f.title)
        if key not in key_map:
            key_map[key] = _GroupedFinding(
                severity=f.severity, check_name=f.check_name, title=f.title
            )
            order[key] = len(order)
        key_map[key].locations.append((f.file, f.line))

    by_severity: dict[Severity, list[_GroupedFinding]] = defaultdict(list)
    for key in sorted(key_map, key=lambda k: order[k]):
        by_severity[key[0]].append(key_map[key])
    return dict(by_severity)


@click.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option(
    "--checks",
    "check_names",
    default=None,
    help=f"Comma-separated check names (default: all). Available: {', '.join(ALL_CHECKS)}",
)
@click.option("--output", "-o", default=None, type=click.Path(), help="Export PDF report to this path.")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text).",
)
@click.option(
    "--sdk-path",
    default=None,
    type=click.Path(exists=True),
    help="Path to a Ren'Py SDK directory. Uses SDK's parser instead of regex.",
)
def analyze(
    project_path: str, check_names: str | None, output: str | None, verbose: bool, fmt: str, sdk_path: str | None
) -> None:
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

    grouped = _group_findings(findings)
    total = len(findings)
    unique = sum(len(glist) for glist in grouped.values())

    # --- Summary header ---
    click.echo("=== Ren'Py Analyzer Results ===")
    parts = []
    for sev in Severity:
        count = sum(len(g.locations) for g in grouped.get(sev, []))
        if count:
            label = click.style(f"{count} {sev.name.lower()}", fg=SEVERITY_COLORS[sev])
            parts.append(label)
    summary = ", ".join(parts)
    click.echo(f"{summary}  ({total} findings, {unique} unique)")

    # --- Severity sections ---
    for sev in Severity:
        glist = grouped.get(sev)
        if not glist:
            continue
        sev_count = sum(len(g.locations) for g in glist)
        header = click.style(
            f"-- {sev.name} ({sev_count}) ", fg=SEVERITY_COLORS[sev], bold=True
        )
        click.echo()
        click.echo(header + "-" * max(0, 60 - len(f"-- {sev.name} ({sev_count}) ")))

        for g in glist:
            check_tag = click.style(f"[{g.check_name}]", dim=True)
            if len(g.locations) == 1:
                f, ln = g.locations[0]
                loc = click.style(f"{f}:{ln}", dim=True)
                click.echo(f"  {loc}  {g.title}  {check_tag}")
            else:
                count_tag = click.style(f"({len(g.locations)} locations)", dim=True)
                click.echo(f"  {g.title}  {check_tag}  {count_tag}")
                shown = g.locations[:_MAX_LOCATIONS_SHOWN]
                loc_strs = [f"{f}:{ln}" for f, ln in shown]
                click.echo(click.style(f"      {', '.join(loc_strs)}", dim=True))
                remaining = len(g.locations) - _MAX_LOCATIONS_SHOWN
                if remaining > 0:
                    click.echo(click.style(f"      (+{remaining} more)", dim=True))

    click.echo(f"\nTotal: {len(findings)} finding(s).", err=True)


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
