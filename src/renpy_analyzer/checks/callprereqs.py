"""Check for missing prerequisite variables at call sites.

Labels can declare required variables with a ``# @requires:`` comment
immediately above the label definition::

    # @requires: _sms_char, _sms_queue
    label sms_exchange:
        ...

Every ``call sms_exchange`` site is then checked: the required variables
must be assigned (via ``$`` or augmented ``$`` assignment) somewhere
between the start of the containing label and the call line.
"""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity
from ..parser import RE_LABEL

# Matches ``# @requires: var1, var2, var3``
RE_REQUIRES = re.compile(r"^\s*#\s*@requires:\s*(.+)", re.IGNORECASE)

# Matches ``$ var = ...`` or ``$ var += ...`` (any augmented assignment).
RE_DOLLAR_ASSIGN = re.compile(r"^\s*\$\s+([\w.]+)\s*(?:[+\-*/]?=)")


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # --- Phase 1: collect @requires annotations ---
    requirements: dict[str, list[str]] = {}
    _collect_requirements(project, requirements)

    if not requirements:
        return findings

    # --- Phase 2: build label-name set for quick lookup ---
    label_names = {label.name for label in project.labels}

    # --- Phase 3: check each call site ---
    for call in project.calls:
        if call.target not in requirements:
            continue
        if call.target not in label_names:
            continue  # missing label — handled by labels check

        required_vars = requirements[call.target]
        assigned = _vars_assigned_before(project, call.file, call.line)

        missing = [v for v in required_vars if v not in assigned]
        if missing:
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="callprereqs",
                    title=f"Call to '{call.target}' missing prerequisites",
                    description=(
                        f"Label '{call.target}' requires "
                        f"{', '.join(missing)} to be assigned before the "
                        f"call (line {call.line}), but "
                        f"{'they are' if len(missing) > 1 else 'it is'} "
                        f"not set in the preceding code."
                    ),
                    file=call.file,
                    line=call.line,
                    suggestion=(
                        f"Add '$ {missing[0]} = ...' (and any other "
                        f"missing variables) before the call."
                    ),
                )
            )

    return findings


def _collect_requirements(
    project: ProjectModel,
    out: dict[str, list[str]],
) -> None:
    """Scan raw lines for ``# @requires:`` comments above label defs."""
    for _rel_path, lines in project.raw_lines.items():
        pending_requires: list[str] | None = None

        for raw_line in lines:
            stripped = raw_line.strip()

            # Check for @requires comment.
            m_req = RE_REQUIRES.match(stripped)
            if m_req:
                vars_str = m_req.group(1)
                pending_requires = [
                    v.strip() for v in vars_str.split(",") if v.strip()
                ]
                continue

            # If we have a pending @requires, check if next non-comment
            # line is a label.  Blank lines break the association.
            if pending_requires is not None:
                if not stripped:
                    pending_requires = None
                    continue
                if stripped.startswith("#"):
                    # Another comment is fine — keep pending.
                    continue

                m_label = RE_LABEL.match(raw_line)
                if m_label:
                    label_name = m_label.group(2)
                    out[label_name] = pending_requires
                pending_requires = None


def _vars_assigned_before(
    project: ProjectModel,
    file: str,
    call_line: int,
) -> set[str]:
    """Find variables assigned via ``$`` between the containing label start
    and *call_line* in the same file.
    """
    lines = project.raw_lines.get(file)
    if lines is None:
        return set()

    # Walk backwards from call_line to find the containing label.
    label_start = 0
    for i in range(call_line - 2, -1, -1):  # call_line is 1-based
        if RE_LABEL.match(lines[i]):
            label_start = i + 1  # body starts after the label line
            break

    assigned: set[str] = set()
    for i in range(label_start, call_line - 1):  # up to (not including) call
        m = RE_DOLLAR_ASSIGN.match(lines[i])
        if m:
            assigned.add(m.group(1))

    return assigned
