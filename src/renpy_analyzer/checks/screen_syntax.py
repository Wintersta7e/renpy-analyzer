"""Check for screen language syntax issues.

Detects:
- Ternary ``if/else`` expressions used in screen property lines (Ren'Py
  interprets ``if`` as a block keyword, not a Python ternary).
- Invalid property usage on screen statements (e.g. ``padding`` on ``vbox``).
"""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity

# ---------------------------------------------------------------------------
# Ternary ``if`` detection
# ---------------------------------------------------------------------------

# Known screen property keywords that take a value expression.
_SCREEN_PROPERTIES = frozenset({
    "action", "alternate", "value", "background", "foreground",
    "hover_sound", "activate_sound", "sensitive", "selected",
    "child", "hover", "idle", "insensitive",
    "selected_hover", "selected_idle", "selected_insensitive",
    "text_align", "text_style", "tooltip",
    # Position / size properties that also accept expressions.
    "xpos", "ypos", "xalign", "yalign", "xanchor", "yanchor",
    "alpha", "rotate", "zoom",
    "xsize", "ysize", "color", "style", "focus", "default",
})

# ---------------------------------------------------------------------------
# Conflicting position properties
# ---------------------------------------------------------------------------

# In Ren'Py, ``xalign`` sets both ``xpos`` and ``xanchor`` internally.
# Using ``xalign`` together with ``xpos`` or ``xanchor`` on the same
# displayable is rejected at runtime.  Same for the y-axis equivalents.
_POSITION_CONFLICTS: dict[str, frozenset[str]] = {
    "xalign": frozenset({"xpos", "xanchor"}),
    "xpos": frozenset({"xalign"}),
    "xanchor": frozenset({"xalign"}),
    "yalign": frozenset({"ypos", "yanchor"}),
    "ypos": frozenset({"yalign"}),
    "yanchor": frozenset({"yalign"}),
}

_POSITION_PROPS = frozenset(_POSITION_CONFLICTS)

# Compiled pattern for stripping string literals (handles escaped quotes).
_RE_STRIP_DOUBLE = re.compile(r'"(?:[^"\\]|\\.)*"')
_RE_STRIP_SINGLE = re.compile(r"'(?:[^'\\]|\\.)*'")

# ---------------------------------------------------------------------------
# Invalid property→statement mapping
# ---------------------------------------------------------------------------

# ``padding`` and its directional variants are Window properties — not valid
# on pure layout containers.
_PADDING_PROPERTIES = frozenset({
    "padding", "left_padding", "right_padding",
    "top_padding", "bottom_padding",
    "xpadding", "ypadding",
})

# Layout containers that do NOT accept padding.
_NO_PADDING_STATEMENTS = frozenset({
    "vbox", "hbox", "grid", "fixed", "side", "vpgrid",
})

# ``action`` is only valid on interactive displayables.
_NO_ACTION_STATEMENTS = frozenset({
    "vbox", "hbox", "grid", "fixed", "side",
    "frame", "window", "viewport", "vpgrid",
    "text", "add", "image", "null",
})

# Allowlist of known screen displayable statements.  Only these are pushed
# onto ``stmt_stack`` for property validation.  Control-flow keywords
# (if, for, else, etc.) are intentionally excluded — they are transparent
# wrappers and should not affect property→parent attribution.
_DISPLAYABLE_STATEMENTS = frozenset({
    "vbox", "hbox", "grid", "fixed", "side",
    "frame", "window", "viewport", "vpgrid",
    "button", "textbutton", "imagebutton",
    "text", "add", "image", "null",
    "bar", "vbar", "hotspot", "hotbar",
    "key", "timer", "mousearea",
    "label", "input", "drag", "draggroup",
    "imagemap", "transform",
})

# Property assignment regex: ``  property_keyword <value>``
RE_PROPERTY = re.compile(r"^(\s+)(\w+)\s+(.+)")

# Screen statement regex: ``  statement_keyword:`` or ``  statement_keyword <params>:``
RE_SCREEN_STMT = re.compile(r"^(\s+)(\w+)\s*(?:\(.*\))?\s*:")


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    for rel_path, lines in project.raw_lines.items():
        _check_file(rel_path, lines, findings)

    return findings


def _check_file(rel_path: str, lines: list[str], findings: list[Finding]) -> None:
    in_screen = False

    # Stack of (statement_name, indent, lineno) for nested screen statements.
    stmt_stack: list[tuple[str, int, int]] = []

    # Position properties seen per element, keyed by element's line number.
    element_pos_props: dict[int, list[tuple[str, int]]] = {}

    for lineno_0, raw_line in enumerate(lines):
        lineno = lineno_0 + 1
        line = raw_line.rstrip()

        if not line or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # Track screen blocks (column 0).
        if indent == 0:
            if re.match(r"^screen\s+\w+", line):
                in_screen = True
                stmt_stack.clear()
                continue
            elif in_screen:
                # Another top-level definition — screen ended.
                in_screen = False
                stmt_stack.clear()
                continue

        if not in_screen:
            continue

        # Pop statements from the stack that are no longer parents.
        while stmt_stack and indent <= stmt_stack[-1][1]:
            stmt_stack.pop()

        # Check for screen sub-statement (e.g. ``vbox:``, ``button:``)
        m_stmt = RE_SCREEN_STMT.match(line)
        if m_stmt:
            stmt_name = m_stmt.group(2)
            # Only push known displayable statements onto the stack.
            if stmt_name in _DISPLAYABLE_STATEMENTS:
                stmt_stack.append((stmt_name, indent, lineno))
            continue

        # --- Check properties ---
        m_prop = RE_PROPERTY.match(line)
        if not m_prop:
            continue

        prop_name = m_prop.group(2)
        prop_value = m_prop.group(3).rstrip()

        # Skip lines that end with ``:`` (sub-statements, not properties).
        if prop_value.endswith(":"):
            if prop_name in _DISPLAYABLE_STATEMENTS:
                stmt_stack.append((prop_name, indent, lineno))
            continue

        # --- Conflicting position properties ---
        if prop_name in _POSITION_PROPS and stmt_stack:
            elem_key = stmt_stack[-1][2]  # parent element's line number
            seen = element_pos_props.setdefault(elem_key, [])
            conflicts = _POSITION_CONFLICTS[prop_name]
            for prev_name, prev_line in seen:
                if prev_name in conflicts:
                    findings.append(
                        Finding(
                            severity=Severity.HIGH,
                            check_name="screen_syntax",
                            title="Conflicting position properties",
                            description=(
                                f"'{prop_name}' (line {lineno}) conflicts "
                                f"with '{prev_name}' (line {prev_line}) on "
                                f"the same element. Ren'Py rejects this "
                                f"combination at runtime."
                            ),
                            file=rel_path,
                            line=lineno,
                            suggestion=(
                                f"Remove either '{prop_name}' or "
                                f"'{prev_name}'. 'xalign' sets both xpos "
                                f"and xanchor internally; 'yalign' sets "
                                f"both ypos and yanchor."
                            ),
                        )
                    )
            seen.append((prop_name, lineno))

        # --- Ternary if/else detection ---
        if (prop_name in _SCREEN_PROPERTIES or prop_name.startswith(("selected_", "hover_", "idle_", "insensitive_"))) and re.search(r"\bif\b", prop_value) and re.search(r"\belse\b", prop_value):
            # Strip string literals (handles escaped quotes) before checking.
            stripped = _RE_STRIP_DOUBLE.sub('', prop_value)
            stripped = _RE_STRIP_SINGLE.sub('', stripped)
            if re.search(r"\bif\b", stripped) and re.search(r"\belse\b", stripped):
                findings.append(
                    Finding(
                        severity=Severity.CRITICAL,
                        check_name="screen_syntax",
                        title="Ternary if/else in screen property",
                        description=(
                            f"'{prop_name} {prop_value}' uses an inline "
                            f"if/else expression. Ren'Py's screen parser "
                            f"interprets 'if' as a block keyword here, "
                            f"causing a parse error."
                        ),
                        file=rel_path,
                        line=lineno,
                        suggestion=(
                            "Move the ternary expression to a $ assignment "
                            "above the screen statement, then reference the "
                            "variable in the property."
                        ),
                    )
                )

        # --- Invalid property on parent statement ---
        if not stmt_stack:
            continue

        parent_stmt = stmt_stack[-1][0]

        # Padding on layout containers.
        if prop_name in _PADDING_PROPERTIES and parent_stmt in _NO_PADDING_STATEMENTS:
            findings.append(
                Finding(
                    severity=Severity.CRITICAL,
                    check_name="screen_syntax",
                    title=f"Invalid property '{prop_name}' on '{parent_stmt}'",
                    description=(
                        f"'{prop_name}' is not a valid property of "
                        f"'{parent_stmt}'. Padding is only valid on "
                        f"window-like displayables (frame, window, button)."
                    ),
                    file=rel_path,
                    line=lineno,
                    suggestion=(
                        f"Wrap the {parent_stmt} content in a 'frame' with "
                        f"'background None' and set '{prop_name}' on the frame, "
                        f"or use xoffset/yoffset for positioning."
                    ),
                )
            )

        # Action on non-interactive displayables.
        if prop_name == "action" and parent_stmt in _NO_ACTION_STATEMENTS:
            findings.append(
                Finding(
                    severity=Severity.CRITICAL,
                    check_name="screen_syntax",
                    title=f"Invalid property 'action' on '{parent_stmt}'",
                    description=(
                        f"'action' is not a valid property of '{parent_stmt}'. "
                        f"Only interactive displayables (button, textbutton, "
                        f"imagebutton, etc.) accept 'action'."
                    ),
                    file=rel_path,
                    line=lineno,
                    suggestion=(
                        "Wrap the content in a 'button:' block and set "
                        "'action' on the button."
                    ),
                )
            )
