"""Check for screen definition issues: undefined refs, duplicates, unused defs."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity

BUILTIN_SCREENS = frozenset(
    {
        "say",
        "choice",
        "nvl",
        "notify",
        "confirm",
        "preferences",
        "save",
        "load",
        "main_menu",
        "about",
        "help",
        "keyboard_help",
        "game_menu",
        "quick_menu",
        "text_history",
        "skip_indicator",
        "ctc",
    }
)


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Index definitions
    defined: dict[str, list] = {}
    for sd in project.screen_defs:
        defined.setdefault(sd.name, []).append(sd)

    # Duplicate screen definitions
    for name, defs in defined.items():
        if len(defs) > 1:
            first = defs[0]
            locations = ", ".join(f"{d.file}:{d.line}" for d in defs)
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="screens",
                    title=f"Duplicate screen '{name}'",
                    description=(
                        f"Screen '{name}' is defined {len(defs)} times: {locations}. "
                        f"Only the last definition will be used."
                    ),
                    file=first.file,
                    line=first.line,
                    suggestion="Remove duplicate definitions.",
                )
            )

    # Index references
    ref_names: set[str] = set()
    ref_locations: dict[str, list] = {}
    for sr in project.screen_refs:
        ref_names.add(sr.name)
        ref_locations.setdefault(sr.name, []).append(sr)

    # Undefined screen references
    for name, refs in ref_locations.items():
        if name not in defined and name not in BUILTIN_SCREENS:
            first = refs[0]
            if len(refs) > 1:
                count_note = f" (and {len(refs) - 1} other location{'s' if len(refs) > 2 else ''})"
            else:
                count_note = ""
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="screens",
                    title=f"Undefined screen '{name}'",
                    description=(
                        f"Screen '{name}' is referenced via '{first.action} screen' at "
                        f"{first.file}:{first.line}{count_note} but is never defined."
                    ),
                    file=first.file,
                    line=first.line,
                    suggestion=f"Define 'screen {name}:' or check for typos.",
                )
            )

    # Unused screen definitions
    for name, defs in defined.items():
        if name not in ref_names and name not in BUILTIN_SCREENS:
            d = defs[0]
            findings.append(
                Finding(
                    severity=Severity.LOW,
                    check_name="screens",
                    title=f"Unused screen '{name}'",
                    description=(
                        f"Screen '{name}' defined at {d.file}:{d.line} "
                        f"is never referenced with show/call/hide screen."
                    ),
                    file=d.file,
                    line=d.line,
                    suggestion="Remove if no longer needed.",
                )
            )

    return findings
