"""Check for menu issues: empty choices, fallthroughs, single-option menus."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    for menu in project.menus:
        if len(menu.choices) == 1:
            findings.append(
                Finding(
                    severity=Severity.LOW,
                    check_name="menus",
                    title="Single-choice menu",
                    description=(
                        f"Menu at {menu.file}:{menu.line} has only one choice: "
                        f"'{menu.choices[0].text}'. This offers no real player decision."
                    ),
                    file=menu.file,
                    line=menu.line,
                    suggestion="Add more choices or remove the menu wrapper.",
                )
            )

        if len(menu.choices) < 2:
            continue

        max_content = max(c.content_lines for c in menu.choices)

        for choice in menu.choices:
            if choice.content_lines == 0:
                findings.append(
                    Finding(
                        severity=Severity.HIGH,
                        check_name="menus",
                        title=f"Empty menu choice: '{choice.text}'",
                        description=(
                            f"Menu choice '{choice.text}' at {menu.file}:{choice.line} "
                            f"has no content — execution falls through immediately."
                        ),
                        file=menu.file,
                        line=choice.line,
                        suggestion="Add content to this choice or remove it.",
                    )
                )
            elif choice.content_lines <= 1 and not choice.has_jump and not choice.has_return and max_content > 2:
                findings.append(
                    Finding(
                        severity=Severity.MEDIUM,
                        check_name="menus",
                        title=f"Possible menu fallthrough: '{choice.text}'",
                        description=(
                            f"Menu choice '{choice.text}' at {menu.file}:{choice.line} "
                            f"has only {choice.content_lines} line(s) while sibling choices "
                            f"have up to {max_content}. Content after the menu block may "
                            f"play regardless of which choice was picked."
                        ),
                        file=menu.file,
                        line=choice.line,
                        suggestion="Verify this is intentional, or add a jump/return.",
                    )
                )

    return findings
