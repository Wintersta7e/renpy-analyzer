"""Check for variable issues: undeclared, unused, case mismatches."""

from __future__ import annotations

import re
from collections import Counter

from ..models import Finding, ProjectModel, Severity

PYTHON_BUILTINS = frozenset({
    "list", "dict", "set", "str", "int", "float", "bool", "tuple", "type",
    "True", "False", "None", "print", "len", "range", "map", "filter",
    "zip", "enumerate", "sorted", "reversed", "min", "max", "sum", "abs",
    "all", "any", "input", "open", "format", "id", "hash", "repr",
    "object", "super", "property", "classmethod", "staticmethod",
})


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    defaults: dict[str, list] = {}
    all_refs: set[str] = set()

    for var in project.variables:
        if var.kind == "default":
            defaults.setdefault(var.name, []).append(var)
        elif var.kind in ("assign", "augment"):
            all_refs.add(var.name)

    # Duplicate defaults
    for name, defs in defaults.items():
        if len(defs) > 1:
            locations = ", ".join(f"{d.file}:{d.line}" for d in defs)
            for d in defs:
                findings.append(Finding(
                    severity=Severity.HIGH,
                    check_name="variables",
                    title=f"Duplicate default '{name}'",
                    description=(
                        f"Variable '{name}' is declared with 'default' {len(defs)} "
                        f"times: {locations}. Only one declaration will take effect."
                    ),
                    file=d.file,
                    line=d.line,
                    suggestion="Remove duplicate declarations — keep one 'default' in your variables file.",
                ))

    for cond in project.conditions:
        for name in re.findall(r'\b([A-Za-z_]\w*)\b', cond.expression):
            if name not in ("True", "False", "None", "and", "or", "not",
                            "if", "elif", "else", "in", "is"):
                all_refs.add(name)

    for dl in project.dialogue:
        all_refs.add(dl.speaker)

    # Case mismatch detection — two strategies:
    # 1. Exact name collision (same name, different casing): myVar vs myvar
    # 2. Pattern-based (numbered family with inconsistent casing): foo_slow_1 vs foo_Slow_3

    # Strategy 1: exact lowercase collision
    lower_map: dict[str, list[str]] = {}
    for name in defaults:
        if "." in name:
            continue
        lower_map.setdefault(name.lower(), []).append(name)

    reported_names: set[str] = set()
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
                reported_names.add(vname)

    # Strategy 2: pattern-based — strip trailing digits to find families
    # e.g., marysex4_slow_1, marysex4_slow_2, marysex4_Slow_3
    #   all share base "marysex4_slow_" (lowered), but one has different casing
    family_map: dict[str, list[str]] = {}  # lowered_base -> [original names]
    for name in defaults:
        if "." in name or name in reported_names:
            continue
        base = re.sub(r'\d+$', '', name)  # strip trailing digits
        if base != name:  # only if there was a trailing number
            family_map.setdefault(base.lower(), []).append(name)

    for base_lower, members in family_map.items():
        if len(members) < 2:
            continue
        # Check if any member has different casing in the non-digit prefix
        bases = [re.sub(r'\d+$', '', m) for m in members]
        if len(set(bases)) > 1:  # different casing in the base part
            # Find the outlier (minority casing)
            base_counts = Counter(bases)
            majority_base = base_counts.most_common(1)[0][0]
            for m, b in zip(members, bases):
                if b != majority_base:
                    var = defaults[m][0]
                    expected = majority_base + re.search(r'\d+$', m).group()
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        check_name="variables",
                        title=f"Variable case mismatch: '{m}'",
                        description=(
                            f"Variable '{m}' at {var.file}:{var.line} breaks the "
                            f"casing pattern of its family "
                            f"({', '.join(sorted(members))}). "
                            f"Expected '{expected}' to match siblings."
                        ),
                        file=var.file,
                        line=var.line,
                        suggestion=f"Rename to '{expected}' to match the family pattern.",
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

    # Mutable define: define X then $ X = / $ X +=
    defined_vars = {}
    for var in project.variables:
        if var.kind == "define" and "." not in var.name:
            defined_vars.setdefault(var.name, var)

    for var in project.variables:
        if var.kind in ("assign", "augment") and var.name in defined_vars:
            defn = defined_vars[var.name]
            findings.append(Finding(
                severity=Severity.CRITICAL,
                check_name="variables",
                title=f"Defined variable '{var.name}' mutated",
                description=(
                    f"Variable '{var.name}' is declared with 'define' at "
                    f"{defn.file}:{defn.line} but modified at {var.file}:{var.line}. "
                    f"'define' variables are NOT saved in save files — changes are "
                    f"lost on load. Use 'default' instead of 'define' for any "
                    f"variable that changes during gameplay."
                ),
                file=var.file,
                line=var.line,
                suggestion=f"Change 'define {var.name} = ...' to 'default {var.name} = ...'.",
            ))

    # define persistent.X misuse
    for var in project.variables:
        if var.kind == "define" and var.name.startswith("persistent."):
            findings.append(Finding(
                severity=Severity.HIGH,
                check_name="variables",
                title=f"Persistent variable '{var.name}' uses define",
                description=(
                    f"'{var.name}' at {var.file}:{var.line} is declared with 'define' "
                    f"but persistent variables must use 'default' to work correctly "
                    f"across saves and game sessions."
                ),
                file=var.file,
                line=var.line,
                suggestion=f"Change 'define {var.name}' to 'default {var.name}'.",
            ))

    # Builtin name shadowing
    for var in project.variables:
        if var.kind in ("default", "define") and var.name in PYTHON_BUILTINS:
            findings.append(Finding(
                severity=Severity.HIGH,
                check_name="variables",
                title=f"Variable '{var.name}' shadows Python builtin",
                description=(
                    f"Variable '{var.name}' at {var.file}:{var.line} shadows a "
                    f"Python builtin. This can cause cryptic errors when Ren'Py "
                    f"or Python code tries to use the original builtin."
                ),
                file=var.file,
                line=var.line,
                suggestion=f"Rename '{var.name}' to avoid shadowing the Python builtin.",
            ))

    return findings
