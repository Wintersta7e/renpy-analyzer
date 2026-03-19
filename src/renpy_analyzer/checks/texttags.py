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
                # Do NOT pop — the opening tag is still unclosed
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


def _extract_brackets(text: str) -> list[tuple[str, int, bool]]:
    """Extract bracket expressions from text, handling escapes and nesting.

    Returns ``(expression_content, start_position, closed)`` tuples.
    *closed* is True when the bracket was properly terminated with ``]``,
    False when end-of-string was reached with the bracket still open.
    Skips ``[[`` escape sequences.  Tracks quote and bracket depth so that
    ``]`` inside strings or nested ``[...]`` does not close prematurely.
    """
    results: list[tuple[str, int, bool]] = []
    i = 0
    length = len(text)

    while i < length:
        c = text[i]

        # [[ escape — skip both chars
        if c == "[" and i + 1 < length and text[i + 1] == "[":
            i += 2
            continue

        if c == "[":
            # Start capturing expression
            start = i
            i += 1
            depth = 1
            buf: list[str] = []
            in_quote: str | None = None  # current quote delimiter or None

            while i < length and depth > 0:
                ch = text[i]

                # Handle quoted strings inside expression
                if in_quote is not None:
                    buf.append(ch)
                    # Check for matching end quote (triple or single)
                    if len(in_quote) == 3:
                        if text[i : i + 3] == in_quote:
                            buf.append(text[i + 1])
                            buf.append(text[i + 2])
                            i += 3
                            in_quote = None
                            continue
                    elif ch == in_quote and (i == 0 or text[i - 1] != "\\"):
                        in_quote = None
                    i += 1
                    continue

                # Check for start of quoted string
                if ch in ('"', "'"):
                    # Triple quote?
                    if i + 2 < length and text[i + 1] == ch and text[i + 2] == ch:
                        in_quote = ch * 3
                        buf.append(ch)
                        buf.append(text[i + 1])
                        buf.append(text[i + 2])
                        i += 3
                        continue
                    else:
                        in_quote = ch
                        buf.append(ch)
                        i += 1
                        continue

                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        results.append(("".join(buf), start, True))
                        i += 1
                        break

                buf.append(ch)
                i += 1
            else:
                # End of string with unclosed bracket
                if depth > 0:
                    results.append(("".join(buf), start, False))
        else:
            i += 1

    return results


def _find_depth0_char(expr: str, char: str) -> int:
    """Find the last occurrence of *char* at depth 0 (outside parens, brackets, quotes).

    Returns the index, or -1 if not found.  Scans left-to-right, collecting
    all depth-0 matches, and returns the rightmost one.
    For ``!``, skips ``!=`` (operator, not conversion separator).
    """
    paren = 0  # ()
    bracket = 0  # []
    in_quote: str | None = None
    depth0_positions: list[int] = []
    i = 0
    length = len(expr)

    while i < length:
        ch = expr[i]

        if in_quote is not None:
            if len(in_quote) == 3:
                if expr[i : i + 3] == in_quote:
                    i += 3
                    in_quote = None
                    continue
            elif ch == in_quote and (i == 0 or expr[i - 1] != "\\"):
                in_quote = None
            i += 1
            continue

        if ch in ('"', "'"):
            if i + 2 < length and expr[i + 1] == ch and expr[i + 2] == ch:
                in_quote = ch * 3
                i += 3
                continue
            else:
                in_quote = ch
                i += 1
                continue

        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == char and paren == 0 and bracket == 0:
            # For '!', skip '!=' (operator)
            if char == "!" and i + 1 < length and expr[i + 1] == "=":
                i += 1
            else:
                depth0_positions.append(i)
        i += 1

    return depth0_positions[-1] if depth0_positions else -1


def _strip_renpy_suffixes(expr: str) -> str:
    """Strip Ren'Py interpolation suffixes: format spec, conversion flags, debug ``=``.

    Stripping order (outermost first, right-to-left):
    1. ``:format_spec`` — outermost ``:`` at depth 0
    2. ``!conversion_flags`` — outermost ``!`` at depth 0 (skip ``!=``)
    3. ``=`` debug suffix — trailing ``=`` that is not ``==``, ``!=``, ``<=``, ``>=``
    """
    # 1. Strip format spec
    colon_pos = _find_depth0_char(expr, ":")
    if colon_pos > 0:
        expr = expr[:colon_pos]

    # 2. Strip conversion flags
    bang_pos = _find_depth0_char(expr, "!")
    if bang_pos > 0:
        expr = expr[:bang_pos]

    # 3. Strip debug = suffix
    stripped = expr.rstrip()
    if stripped.endswith("=") and not stripped.endswith(("==", "!=", "<=", ">=")):
        expr = stripped[:-1]

    return expr


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
