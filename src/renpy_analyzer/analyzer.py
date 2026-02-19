"""Core analysis engine — shared by GUI and CLI."""

from __future__ import annotations

import logging
from typing import Callable

from .checks import ALL_CHECKS
from .models import Finding
from .project import load_project

logger = logging.getLogger("renpy_analyzer.analyzer")


def run_analysis(
    project_path: str,
    checks: list[str] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
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

    _progress("Parsing project files...", 0.0)
    project = load_project(project_path)
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

    findings.sort(key=lambda f: f.severity)
    logger.info("Analysis complete: %d findings from %d checks", len(findings), total)
    _progress("Analysis complete.", 1.0)
    return findings
