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

        if body.has_return and body.ends_with_jump:
            # Conditional return + unconditional jump — stack leak on non-return path
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="callreturn",
                    title=f"Called label '{target}' may not return (conditional)",
                    description=(
                        f"'call {target}' at {call.file}:{call.line} targets a label "
                        f"with a conditional 'return' but ends with 'jump'. On the "
                        f"non-returning path, the call stack frame leaks."
                    ),
                    file=call.file,
                    line=call.line,
                    suggestion=f"Ensure all code paths in label '{target}' reach a 'return'.",
                )
            )
        elif not body.has_return:
            if body.ends_with_jump:
                # Label ends with jump — stack frame leaks
                findings.append(
                    Finding(
                        severity=Severity.HIGH,
                        check_name="callreturn",
                        title=f"Called label '{target}' jumps instead of returning",
                        description=(
                            f"'call {target}' at {call.file}:{call.line} targets a label "
                            f"that ends with a 'jump' instead of 'return'. The call stack "
                            f"frame is never popped — over many calls this leaks memory "
                            f"and eventually crashes."
                        ),
                        file=call.file,
                        line=call.line,
                        suggestion=f"Replace 'jump' with 'return' at the end of label '{target}', or use 'jump' instead of 'call' at the call site.",
                    )
                )
            else:
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
