"""Check for labels with empty bodies (no content or only 'pass')."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity
from ._label_body import analyze_label_bodies


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []
    bodies = analyze_label_bodies(project)

    for name, body in bodies.items():
        if body.body_lines == 0 or body.only_pass:
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="emptylabels",
                    title=f"Empty label '{name}'",
                    description=(
                        f"Label '{name}' at {body.file}:{body.line} has no meaningful "
                        f"content{' (only pass)' if body.only_pass else ''}. "
                        f"In Ren'Py, an empty label falls through to whatever code "
                        f"follows it in the file, which is almost certainly unintended."
                    ),
                    file=body.file,
                    line=body.line,
                    suggestion=f"Add content to label '{name}' or remove it if it's a leftover stub.",
                )
            )

    return findings
