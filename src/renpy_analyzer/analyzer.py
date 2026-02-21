"""Core analysis engine — shared by GUI and CLI."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .checks import ALL_CHECKS
from .models import Finding, Severity
from .project import load_project

logger = logging.getLogger("renpy_analyzer.analyzer")


def run_analysis(
    project_path: str,
    checks: list[str] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    sdk_path: str | None = None,
) -> list[Finding]:
    """Run analysis on a Ren'Py project and return sorted findings.

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

    parser_label = "SDK" if sdk_path else "regex"
    _progress(f"Parsing project files ({parser_label} parser)...", 0.0)
    project = load_project(project_path, sdk_path=sdk_path)
    _progress(f"Parsed {len(project.files)} .rpy files ({parser_label} parser).", 0.1)

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

    # Warn if the selected directory contains multiple separate game projects
    if project.multi_game_dirs:
        dirs = project.multi_game_dirs
        dir_list = ", ".join(dirs[:5]) + ("..." if len(dirs) > 5 else "")
        findings.insert(
            0,
            Finding(
                severity=Severity.MEDIUM,
                check_name="project",
                title="Multiple game projects detected",
                description=(
                    f"The selected directory contains {len(dirs)} separate game projects: "
                    f"{dir_list}. "
                    f"Analyzing them together may produce false positives "
                    f"(duplicate labels, cross-project references). "
                    f"For accurate results, point the analyzer at a single game directory."
                ),
                file="",
                line=0,
                suggestion="Select a specific game subdirectory instead of the parent folder.",
            ),
        )

    findings.sort(key=lambda f: f.severity)
    logger.info("Analysis complete: %d findings from %d checks", len(findings), total)
    _progress("Analysis complete.", 1.0)
    return findings
