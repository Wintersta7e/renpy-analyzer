"""Check for text tag issues in dialogue: unclosed, mismatched, unknown tags."""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity

# Tags that require a closing {/tag}
PAIRED_TAGS = frozenset(
    {
        "b",
        "i",
        "u",
        "s",
        "plain",
        "a",
        "font",
        "size",
        "color",
        "outlinecolor",
        "alpha",
        "k",
        "cps",
        "rt",
        "rb",
        "alt",
        "noalt",
    }
)

# Tags that are self-closing (no closing tag needed)
SELF_CLOSING_TAGS = frozenset(
    {
        "w",
        "p",
        "nw",
        "fast",
        "space",
        "vspace",
        "image",
        "clear",
        "done",
        "#",
        "lb",
    }
)

ALL_KNOWN_TAGS = PAIRED_TAGS | SELF_CLOSING_TAGS

# Matches {tag}, {tag=value}, {/tag}
RE_TEXT_TAG = re.compile(r"\{(/?\w+|#)(?:=[^}]*)?\}")


def _validate_tags(text: str) -> list[str]:
    """Validate text tags in a dialogue string.

    Returns a list of error messages (empty if no issues).
    """
    errors: list[str] = []
    stack: list[str] = []

    for m in RE_TEXT_TAG.finditer(text):
        tag_raw = m.group(1)

        if tag_raw.startswith("/"):
            # Closing tag
            tag_name = tag_raw[1:]
            if not stack:
                errors.append(f"Closing tag '{{/{tag_name}}}' without opening")
            elif stack[-1] != tag_name:
                errors.append(f"Mismatched nesting: expected '{{/{stack[-1]}}}', found '{{/{tag_name}}}'")
                # Pop anyway to avoid cascading errors
                stack.pop()
            else:
                stack.pop()
        else:
            tag_name = tag_raw
            if tag_name not in ALL_KNOWN_TAGS:
                errors.append(f"Unknown text tag '{{{tag_name}}}'")
            elif tag_name in PAIRED_TAGS:
                stack.append(tag_name)

    # Any remaining open tags
    for tag_name in reversed(stack):
        errors.append(f"Unclosed tag '{{{tag_name}}}'")

    return errors


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Deduplicate dialogue lines — the parser may capture the same line
    # via both RE_DIALOGUE and RE_DIALOGUE_FALLBACK
    seen: set[tuple[str, int]] = set()
    unique_dialogue: list = []
    for dl in project.dialogue:
        key = (dl.file, dl.line)
        if key not in seen:
            seen.add(key)
            unique_dialogue.append(dl)

    for dl in unique_dialogue:
        if not dl.text:
            continue

        errors = _validate_tags(dl.text)
        for error_msg in errors:
            # Determine severity
            if "Unknown" in error_msg:
                severity = Severity.LOW
            else:
                severity = Severity.MEDIUM

            findings.append(
                Finding(
                    severity=severity,
                    check_name="texttags",
                    title="Text tag issue",
                    description=f"{error_msg} in dialogue at {dl.file}:{dl.line}.",
                    file=dl.file,
                    line=dl.line,
                    suggestion="Check text tag syntax: paired tags need {{/tag}}, verify tag names.",
                )
            )

    return findings
