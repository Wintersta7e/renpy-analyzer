"""Check for project structure issues: missing label start, reserved filenames."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    _check_missing_start(project, findings)
    _check_reserved_filenames(project, findings)

    return findings


def _check_missing_start(project: ProjectModel, findings: list[Finding]) -> None:
    """Every Ren'Py game must have a 'label start:' — without it the game crashes on launch."""
    label_names = {label.name for label in project.labels}
    if "start" in label_names or not project.files:
        return

    # When scripts may live in .rpa archives or only compiled .rpyc files are
    # present, we can't see the full source — so we can't be certain 'label
    # start' is actually missing. Downgrade to MEDIUM with a qualifying note,
    # matching the behavior of labels.py for missing jump/call targets.
    archived = project.has_rpa or project.has_rpyc_only
    if archived:
        source = ".rpa archives" if project.has_rpa else "compiled .rpyc files"
        description = (
            f"No 'label start:' found in visible .rpy source. This game uses {source} — "
            "the label may exist inside the archived scripts. If it does not, the game "
            "will crash on launch with 'ScriptError: Could not find label start'."
        )
    else:
        description = (
            "No 'label start:' found in any .rpy file. Ren'Py requires this "
            "label as the game entry point — without it the game will crash "
            "on launch with 'ScriptError: Could not find label start'."
        )

    findings.append(
        Finding(
            severity=Severity.MEDIUM if archived else Severity.CRITICAL,
            check_name="structure",
            title="Missing 'label start'",
            description=description,
            file="(project)",
            line=0,
            suggestion="Add 'label start:' to your main script file.",
        )
    )


def _check_reserved_filenames(project: ProjectModel, findings: list[Finding]) -> None:
    """Ren'Py reserves filenames beginning with '00' for engine bootstrap files."""
    root = Path(project.root_dir)
    seen: set[str] = set()
    for filepath in project.files:
        filename = PurePosixPath(filepath).name
        if filename.startswith("00") and filepath not in seen:
            seen.add(filepath)
            # Use relative path for consistency with other checks.
            file_path = Path(filepath)
            rel_path = str(file_path.relative_to(root)) if file_path.is_absolute() else filepath
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="structure",
                    title=f"Reserved filename '{filename}'",
                    description=(
                        f"File '{rel_path}' starts with '00', which is reserved by "
                        f"Ren'Py for engine bootstrap files. This may conflict with "
                        f"built-in scripts and cause unexpected behavior."
                    ),
                    file=rel_path,
                    line=0,
                    suggestion="Rename the file to not start with '00'.",
                )
            )
