"""Check for call statements targeting labels that never return."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity
from ._label_body import analyze_label_bodies


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []
    bodies = analyze_label_bodies(project)

    for call in project.calls:
        target = call.target
        # Skip dynamic calls (expression-based)
        if not target or not target.isidentifier():
            continue

        body = bodies.get(target)
        if body is None:
            # Label not found — handled by labels check
            continue

        if not body.has_return:
            findings.append(
                Finding(
                    severity=Severity.CRITICAL,
                    check_name="callreturn",
                    title=f"Called label '{target}' never returns",
                    description=(
                        f"'call {target}' at {call.file}:{call.line} targets a label "
                        f"that has no 'return' statement. In Ren'Py, 'call' pushes onto "
                        f"the call stack, and without 'return', the stack frame is never "
                        f"popped. Over many calls, this causes a stack overflow crash."
                    ),
                    file=call.file,
                    line=call.line,
                    suggestion=f"Add a 'return' statement at the end of label '{target}', or use 'jump' instead of 'call' if you don't need to return.",
                )
            )

    return findings
