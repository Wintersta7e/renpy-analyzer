"""Check for persistent variables used without default initialization."""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity

RE_PERSISTENT = re.compile(r"persistent\.(\w+)")


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Step 1: Collect all persistent vars declared with 'default'
    declared: set[str] = set()
    for var in project.variables:
        if var.kind == "default" and var.name.startswith("persistent."):
            declared.add(var.name)

    # Step 2: Collect all persistent var READS (not write-only)
    # - Conditions: any persistent.X reference is a read
    # - Augmented assignments (+=, -=, etc.): reads current value
    # - Plain assignments: write-only, don't flag
    reads: dict[str, tuple[str, int]] = {}  # name -> first (file, line)

    for cond in project.conditions:
        for m in RE_PERSISTENT.finditer(cond.expression):
            full_name = f"persistent.{m.group(1)}"
            if full_name not in reads:
                reads[full_name] = (cond.file, cond.line)

    for var in project.variables:
        if var.kind == "augment" and var.name.startswith("persistent.") and var.name not in reads:
            reads[var.name] = (var.file, var.line)

    # Step 3: Find reads without defaults
    for name, (file, line) in sorted(reads.items()):
        if name in declared:
            continue
        # Skip underscore-prefixed vars — these are Ren'Py engine internals
        # (e.g. persistent._file_page, persistent._achievements) initialized
        # by the engine via Python code, not default statements.
        var_suffix = name.split(".", 1)[1] if "." in name else name
        if var_suffix.startswith("_"):
            continue

        findings.append(
            Finding(
                severity=Severity.HIGH,
                check_name="persistent",
                title=f"Persistent variable '{name}' used without default",
                description=(
                    f"'{name}' is referenced at {file}:{line} but never declared "
                    f"with 'default {name} = ...'. On a fresh install, this "
                    f"variable will be None, which may cause TypeError or logic bugs."
                ),
                file=file,
                line=line,
                suggestion=f"Add 'default {name} = <initial_value>' to initialize this persistent variable.",
            )
        )

    return findings
