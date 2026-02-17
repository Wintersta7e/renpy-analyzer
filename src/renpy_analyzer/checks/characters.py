"""Check for character definition issues: undefined speakers, unused defs."""

from __future__ import annotations

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    defined_chars: dict[str, list] = {}
    for char in project.characters:
        defined_chars.setdefault(char.shorthand, []).append(char)

    non_char_defines: set[str] = set()
    for var in project.variables:
        if var.kind == "define" and var.name not in defined_chars:
            non_char_defines.add(var.name)

    speakers_used: set[str] = set()
    speaker_locations: dict[str, list] = {}
    for dl in project.dialogue:
        speakers_used.add(dl.speaker)
        speaker_locations.setdefault(dl.speaker, []).append(dl)

    for speaker, usages in speaker_locations.items():
        if speaker not in defined_chars and speaker not in non_char_defines:
            first = usages[0]
            if len(usages) > 1:
                count_note = (
                    f" (and {len(usages) - 1} other "
                    f"location{'s' if len(usages) > 2 else ''})"
                )
            else:
                count_note = ""
            findings.append(Finding(
                severity=Severity.HIGH,
                check_name="characters",
                title=f"Undefined speaker '{speaker}'",
                description=(
                    f"Speaker '{speaker}' is used in dialogue at "
                    f"{first.file}:{first.line}{count_note} but is never "
                    f"defined with 'define {speaker} = Character(...)'. "
                ),
                file=first.file,
                line=first.line,
                suggestion=f"Add 'define {speaker} = Character(\"Name\")' to your defines file.",
            ))

    for shorthand, defs in defined_chars.items():
        if shorthand not in speakers_used:
            d = defs[0]
            findings.append(Finding(
                severity=Severity.LOW,
                check_name="characters",
                title=f"Unused character '{shorthand}'",
                description=(
                    f"Character '{shorthand}' ('{d.display_name}') defined at "
                    f"{d.file}:{d.line} is never used as a dialogue speaker."
                ),
                file=d.file,
                line=d.line,
                suggestion="Remove if no longer needed.",
            ))

    return findings
