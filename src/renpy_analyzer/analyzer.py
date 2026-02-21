"""Core analysis engine — shared by GUI and CLI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from .checks import ALL_CHECKS
from .models import Finding, Severity
from .project import detect_sub_games, load_project

logger = logging.getLogger("renpy_analyzer.analyzer")


def run_analysis(
    project_path: str,
    checks: list[str] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    sdk_path: str | None = None,
) -> list[Finding]:
    """Run analysis on a Ren'Py project and return sorted findings.

    When the project path contains multiple sub-games (e.g. Season 1,
    Season 2), each is analyzed independently and findings are combined.

    Parameters
    ----------
    project_path:
        Path to the Ren'Py project root (or its game/ subdirectory).
    checks:
        List of check names to run.  *None* means all checks.
    on_progress:
        Optional callback ``(message, fraction)`` for progress updates.
    cancel_check:
        Optional callable returning *True* when the caller wants to abort.
    sdk_path:
        Optional path to a Ren'Py SDK directory.

    Returns
    -------
    list[Finding]
        Findings sorted by severity (most severe first).

    Raises
    ------
    ValueError
        If an unknown check name is provided.
    """
    if checks is None:
        checks = list(ALL_CHECKS.keys())

    unknown = set(checks) - set(ALL_CHECKS.keys())
    if unknown:
        raise ValueError(f"Unknown check(s): {', '.join(sorted(unknown))}")

    def _progress(msg: str, frac: float) -> None:
        if on_progress is not None:
            on_progress(msg, frac)

    def _cancelled() -> bool:
        return cancel_check is not None and cancel_check()

    # Detect multi-subdir layout (e.g. Season 1, Season 2)
    sub_games = detect_sub_games(project_path)
    if sub_games:
        findings = _run_multi_game_analysis(
            project_path, sub_games, checks, _progress, _cancelled, sdk_path,
        )
    else:
        findings = _run_single_analysis(
            project_path, checks, _progress, _cancelled, sdk_path,
        )

    findings.sort(key=lambda f: f.severity)
    logger.info("Analysis complete: %d findings from %d checks", len(findings), len(checks))
    _progress("Analysis complete.", 1.0)
    return findings


def _run_single_analysis(
    project_path: str,
    checks: list[str],
    _progress: Callable[[str, float], None],
    _cancelled: Callable[[], bool],
    sdk_path: str | None,
    file_prefix: str = "",
) -> list[Finding]:
    """Analyze a single game project."""
    parser_label = "SDK" if sdk_path else "regex"
    _progress(f"Parsing {file_prefix or 'project'} files ({parser_label} parser)...", 0.0)
    project = load_project(project_path, sdk_path=sdk_path)
    _progress(f"Parsed {len(project.files)} .rpy files.", 0.1)

    total = len(checks)
    findings: list[Finding] = []

    for idx, check_name in enumerate(checks):
        if _cancelled():
            logger.info("Analysis cancelled by caller")
            return findings
        fraction = 0.1 + 0.85 * (idx / total)
        _progress(f"Running check: {check_name}...", fraction)
        findings.extend(ALL_CHECKS[check_name](project))

    if _cancelled():
        logger.info("Analysis cancelled by caller")
        return findings

    if project.has_rpyc_only:
        findings.insert(
            0,
            Finding(
                severity=Severity.MEDIUM,
                check_name="project",
                title="No .rpy source files found",
                description=(
                    "This game contains only compiled .rpyc files with no .rpy source code. "
                    "The analyzer requires .rpy source files to detect issues. "
                    "The game may work correctly but cannot be analyzed."
                ),
                file="",
                line=0,
                suggestion="Look for an uncompiled version of the game, or use the Ren'Py SDK to decompile .rpyc files.",
            ),
        )

    # Prefix file paths if this is part of a multi-game run
    if file_prefix:
        for f in findings:
            if f.file:
                f.file = f"{file_prefix}/{f.file}"

    return findings


def _run_multi_game_analysis(
    project_path: str,
    sub_games: list[str],
    checks: list[str],
    _progress: Callable[[str, float], None],
    _cancelled: Callable[[], bool],
    sdk_path: str | None,
) -> list[Finding]:
    """Analyze each sub-game independently and combine findings."""
    root = Path(project_path)
    all_findings: list[Finding] = []
    total_sub = len(sub_games)

    _progress(f"Found {total_sub} sub-games, analyzing each independently...", 0.0)
    logger.info("Multi-game analysis: %d sub-games in %s", total_sub, project_path)

    for sub_idx, sub_name in enumerate(sub_games):
        if _cancelled():
            return all_findings

        sub_path = str(root / sub_name)
        base_frac = sub_idx / total_sub
        next_frac = (sub_idx + 1) / total_sub

        def _sub_progress(msg: str, frac: float, _base=base_frac, _span=next_frac - base_frac, _name=sub_name) -> None:
            _progress(f"[{_name}] {msg}", _base + frac * _span)

        sub_findings = _run_single_analysis(
            sub_path, checks, _sub_progress, _cancelled, sdk_path,
            file_prefix=sub_name,
        )
        all_findings.extend(sub_findings)
        logger.info("  %s: %d findings", sub_name, len(sub_findings))

    return all_findings
