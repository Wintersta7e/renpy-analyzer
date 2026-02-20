"""Check for missing and duplicate label definitions."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    label_names: dict[str, list] = {}
    for label in project.labels:
        label_names.setdefault(label.name, []).append(label)

    for jump in project.jumps:
        if jump.target not in label_names:
            findings.append(
                Finding(
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
                )
            )

    for call in project.calls:
        if call.target not in label_names:
            findings.append(
                Finding(
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
                )
            )

    for name, defs in label_names.items():
        if len(defs) > 1:
            locations = ", ".join(f"{d.file}:{d.line}" for d in defs)
            for d in defs:
                findings.append(
                    Finding(
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
                    )
                )

    for dj in project.dynamic_jumps:
        findings.append(
            Finding(
                severity=Severity.MEDIUM,
                check_name="labels",
                title="Dynamic jump/call target",
                description=(
                    f"Expression-based jump/call at {dj.file}:{dj.line}: "
                    f"`{dj.expression}` — target cannot be statically verified. "
                    f"Ensure the expression resolves to a valid label at runtime."
                ),
                file=dj.file,
                line=dj.line,
                suggestion="Consider using a direct label name if the target is known at write time.",
            )
        )

    return findings
