"""Check for operator precedence bugs and == True anti-patterns."""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity

RE_PRECEDENCE_BUG = re.compile(
    r'\b(\w+)\s+(or|and)\s+(\w+)\s*==\s*(True|False)\b'
)

RE_EXPLICIT_BOOL = re.compile(
    r'\b(\w+)\s*==\s*(True|False)\b'
)


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    for cond in project.conditions:
        expr = cond.expression

        for m in RE_PRECEDENCE_BUG.finditer(expr):
            left_var = m.group(1)
            operator = m.group(2)
            right_var = m.group(3)
            bool_val = m.group(4)

            prefix = expr[:m.start()]
            if re.search(r'==\s*$', prefix):
                continue

            findings.append(Finding(
                severity=Severity.CRITICAL,
                check_name="logic",
                title=f"Operator precedence bug: '{left_var} {operator} {right_var} == {bool_val}'",
                description=(
                    f"At {cond.file}:{cond.line}: `{expr}` — Python evaluates this as "
                    f"`{left_var} {operator} ({right_var} == {bool_val})` due to operator "
                    f"precedence. Since `{left_var}` is truthy when non-zero, the "
                    f"`{right_var} == {bool_val}` check is effectively ignored."
                ),
                file=cond.file,
                line=cond.line,
                suggestion=(
                    f"Write as: `{left_var} == {bool_val} {operator} {right_var} == {bool_val}` "
                    f"or better: `{'not ' if bool_val == 'False' else ''}{left_var} "
                    f"{operator} {'not ' if bool_val == 'False' else ''}{right_var}`"
                ),
            ))

        for m in RE_EXPLICIT_BOOL.finditer(expr):
            var_name = m.group(1)
            bool_val = m.group(2)
            if RE_PRECEDENCE_BUG.search(expr):
                continue
            if var_name in ("True", "False", "None"):
                continue
            findings.append(Finding(
                severity=Severity.STYLE,
                check_name="logic",
                title=f"Explicit '== {bool_val}' comparison",
                description=(
                    f"At {cond.file}:{cond.line}: `{expr}` uses "
                    f"`{var_name} == {bool_val}` instead of "
                    f"{'`' + var_name + '`' if bool_val == 'True' else '`not ' + var_name + '`'}."
                ),
                file=cond.file,
                line=cond.line,
                suggestion=(
                    f"Use `{'not ' if bool_val == 'False' else ''}{var_name}` instead."
                ),
            ))

    return findings
