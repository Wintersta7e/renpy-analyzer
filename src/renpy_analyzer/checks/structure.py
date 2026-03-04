"""Check for project structure issues: missing label start, reserved filenames."""

from __future__ import annotations

from pathlib import PurePosixPath

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    _check_missing_start(project, findings)
    _check_reserved_filenames(project, findings)

    return findings


def _check_missing_start(project: ProjectModel, findings: list[Finding]) -> None:
    """Every Ren'Py game must have a 'label start:' — without it the game crashes on launch."""
    label_names = {label.name for label in project.labels}
    if "start" not in label_names and project.files:
        findings.append(
            Finding(
                severity=Severity.CRITICAL,
                check_name="structure",
                title="Missing 'label start'",
                description=(
                    "No 'label start:' found in any .rpy file. Ren'Py requires this "
                    "label as the game entry point — without it the game will crash "
                    "on launch with 'ScriptError: Could not find label start'."
                ),
                file="(project)",
                line=0,
                suggestion="Add 'label start:' to your main script file.",
            )
        )


def _check_reserved_filenames(project: ProjectModel, findings: list[Finding]) -> None:
    """Ren'Py reserves filenames beginning with '00' for engine bootstrap files."""
    seen: set[str] = set()
    for filepath in project.files:
        filename = PurePosixPath(filepath).name
        if filename.startswith("00") and filename not in seen:
            seen.add(filename)
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="structure",
                    title=f"Reserved filename '{filename}'",
                    description=(
                        f"File '{filepath}' starts with '00', which is reserved by "
                        f"Ren'Py for engine bootstrap files. This may conflict with "
                        f"built-in scripts and cause unexpected behavior."
                    ),
                    file=filepath,
                    line=0,
                    suggestion="Rename the file to not start with '00'.",
                )
            )
