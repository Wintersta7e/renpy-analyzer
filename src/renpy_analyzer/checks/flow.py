"""Check for unreachable code after jump/return statements."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Finding, ProjectModel, Severity

RE_JUMP_LINE = re.compile(r"^(\s+)jump\s+\w+\s*$")
RE_RETURN_LINE = re.compile(r"^(\s+)return\s*$")
RE_LABEL_LINE = re.compile(r"^\s*label\s+\w+\s*:")


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []
    root = Path(project.root_dir)

    for file_path_str in project.files:
        file_path = Path(file_path_str)
        if file_path.is_absolute():
            rel_path = str(file_path.relative_to(root))
        else:
            rel_path = file_path_str

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            findings.append(Finding(
                severity=Severity.MEDIUM,
                check_name="flow",
                title="Could not read file for flow analysis",
                description=(
                    f"File '{rel_path}' could not be read: {exc}. "
                    f"Unreachable code analysis was skipped for this file."
                ),
                file=rel_path,
                line=0,
                suggestion="Check file permissions and ensure the file is accessible.",
            ))
            continue

        _check_file(lines, rel_path, findings)

    return findings


def _check_file(lines: list[str], rel_path: str, findings: list[Finding]) -> None:
    for i, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        m = RE_JUMP_LINE.match(line) or RE_RETURN_LINE.match(line)
        if not m:
            continue

        term_indent = len(m.group(1))
        term_kind = "jump" if "jump" in line else "return"
        lineno = i + 1

        # Look at the next non-blank, non-comment line
        for j in range(i + 1, len(lines)):
            next_line = lines[j].rstrip()
            if not next_line or next_line.lstrip().startswith("#"):
                continue

            next_indent = len(next_line) - len(next_line.lstrip())

            # Less indent = outer/parent block, not unreachable
            if next_indent < term_indent:
                break

            # Deeper indent after a terminator = unreachable
            if RE_LABEL_LINE.match(next_line):
                break

            findings.append(Finding(
                severity=Severity.HIGH,
                check_name="flow",
                title=f"Unreachable code after {term_kind}",
                description=(
                    f"Code at {rel_path}:{j + 1} follows a '{term_kind}' at "
                    f"line {lineno} and will never execute."
                ),
                file=rel_path,
                line=j + 1,
                suggestion=f"Remove unreachable code or move it before the '{term_kind}'.",
            ))
            break  # Only report first unreachable line per jump/return
