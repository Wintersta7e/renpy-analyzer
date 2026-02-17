"""Check for variable issues: undeclared, unused, case mismatches."""

from __future__ import annotations
import re
from ..models import ProjectModel, Finding, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    defaults: dict[str, list] = {}
    all_refs: set[str] = set()

    for var in project.variables:
        if var.kind == "default":
            defaults.setdefault(var.name, []).append(var)
        elif var.kind in ("assign", "augment"):
            all_refs.add(var.name)

    for cond in project.conditions:
        for name in re.findall(r'\b([A-Za-z_]\w*)\b', cond.expression):
            if name not in ("True", "False", "None", "and", "or", "not",
                            "if", "elif", "else", "in", "is"):
                all_refs.add(name)

    for dl in project.dialogue:
        all_refs.add(dl.speaker)

    # Case mismatch detection
    lower_map: dict[str, list[str]] = {}
    for name in defaults:
        if "." in name:
            continue
        lower_map.setdefault(name.lower(), []).append(name)

    for lower_name, variants in lower_map.items():
        if len(variants) > 1:
            for vname in variants:
                var = defaults[vname][0]
                others = [v for v in variants if v != vname]
                findings.append(Finding(
                    severity=Severity.HIGH,
                    check_name="variables",
                    title=f"Variable case mismatch: '{vname}'",
                    description=(
                        f"Variable '{vname}' at {var.file}:{var.line} has "
                        f"case-different siblings: {', '.join(others)}. "
                        f"Ren'Py variables are case-sensitive — this likely "
                        f"causes one variant to never be checked correctly."
                    ),
                    file=var.file,
                    line=var.line,
                    suggestion="Standardize the casing of all related variable names.",
                ))

    # Undeclared variables
    declared_names = set(defaults.keys())
    for var in project.variables:
        if var.kind == "define":
            declared_names.add(var.name)

    for var in project.variables:
        if var.kind == "assign" and var.name not in declared_names:
            if "." in var.name:
                continue
            findings.append(Finding(
                severity=Severity.MEDIUM,
                check_name="variables",
                title=f"Undeclared variable '{var.name}'",
                description=(
                    f"Variable '{var.name}' is assigned at {var.file}:{var.line} "
                    f"but was never declared with 'default'. This can cause issues "
                    f"with save/load and Ren'Py's rollback system."
                ),
                file=var.file,
                line=var.line,
                suggestion=f"Add 'default {var.name} = <initial_value>' to your variables file.",
            ))

    # Unused defaults
    for name, var_list in defaults.items():
        if "." in name:
            continue
        if name not in all_refs:
            var = var_list[0]
            findings.append(Finding(
                severity=Severity.LOW,
                check_name="variables",
                title=f"Unused variable '{name}'",
                description=(
                    f"Variable '{name}' is declared at {var.file}:{var.line} "
                    f"but is never referenced in any script file."
                ),
                file=var.file,
                line=var.line,
                suggestion="Remove if no longer needed, or keep for save compatibility.",
            ))

    return findings
