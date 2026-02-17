"""Check for missing and duplicate label definitions."""

from __future__ import annotations
from ..models import ProjectModel, Finding, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    label_names: dict[str, list] = {}
    for label in project.labels:
        label_names.setdefault(label.name, []).append(label)

    for jump in project.jumps:
        if jump.target not in label_names:
            findings.append(Finding(
                severity=Severity.CRITICAL,
                check_name="labels",
                title=f"Missing label '{jump.target}'",
                description=(
                    f"jump {jump.target} at {jump.file}:{jump.line} "
                    f"targets a label that is never defined in any .rpy file. "
                    f"This will crash at runtime."
                ),
                file=jump.file,
                line=jump.line,
                suggestion=f"Add 'label {jump.target}:' or fix the jump target name.",
            ))

    for call in project.calls:
        if call.target not in label_names:
            findings.append(Finding(
                severity=Severity.CRITICAL,
                check_name="labels",
                title=f"Missing label '{call.target}'",
                description=(
                    f"call {call.target} at {call.file}:{call.line} "
                    f"targets a label that is never defined. "
                    f"This will crash at runtime."
                ),
                file=call.file,
                line=call.line,
                suggestion=f"Add 'label {call.target}:' or fix the call target name.",
            ))

    for name, defs in label_names.items():
        if len(defs) > 1:
            locations = ", ".join(f"{d.file}:{d.line}" for d in defs)
            for d in defs:
                findings.append(Finding(
                    severity=Severity.HIGH,
                    check_name="labels",
                    title=f"Duplicate label '{name}'",
                    description=(
                        f"Label '{name}' is defined {len(defs)} times: {locations}. "
                        f"Only one definition will be used at runtime."
                    ),
                    file=d.file,
                    line=d.line,
                    suggestion="Remove or rename duplicate label definitions.",
                ))

    return findings
