"""Check for transform definition issues: undefined refs, duplicates, unused defs."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity

BUILTIN_TRANSFORMS = frozenset(
    {
        "left",
        "right",
        "center",
        "truecenter",
        "topleft",
        "topright",
        "top",
        "bottom",
        "default",
        "reset",
        "flip",
        "offscreenleft",
        "offscreenright",
    }
)


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Index definitions
    defined: dict[str, list] = {}
    for td in project.transform_defs:
        defined.setdefault(td.name, []).append(td)

    # Duplicate transform definitions
    for name, defs in defined.items():
        if len(defs) > 1:
            first = defs[0]
            locations = ", ".join(f"{d.file}:{d.line}" for d in defs)
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="transforms",
                    title=f"Duplicate transform '{name}'",
                    description=(
                        f"Transform '{name}' is defined {len(defs)} times: {locations}. "
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
    for tr in project.transform_refs:
        ref_names.add(tr.name)
        ref_locations.setdefault(tr.name, []).append(tr)

    # Undefined transform references
    for name, refs in ref_locations.items():
        if name not in defined and name not in BUILTIN_TRANSFORMS:
            first = refs[0]
            if len(refs) > 1:
                count_note = f" (and {len(refs) - 1} other location{'s' if len(refs) > 2 else ''})"
            else:
                count_note = ""
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="transforms",
                    title=f"Undefined transform '{name}'",
                    description=(
                        f"Transform '{name}' is used in an 'at' clause at "
                        f"{first.file}:{first.line}{count_note} but is never defined."
                    ),
                    file=first.file,
                    line=first.line,
                    suggestion=f"Define 'transform {name}:' or check for typos.",
                )
            )

    # Unused transform definitions
    for name, defs in defined.items():
        if name not in ref_names and name not in BUILTIN_TRANSFORMS:
            d = defs[0]
            findings.append(
                Finding(
                    severity=Severity.LOW,
                    check_name="transforms",
                    title=f"Unused transform '{name}'",
                    description=(
                        f"Transform '{name}' defined at {d.file}:{d.line} "
                        f"is never referenced in an 'at' clause."
                    ),
                    file=d.file,
                    line=d.line,
                    suggestion="Remove if no longer needed.",
                )
            )

    return findings
