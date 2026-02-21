"""Shared helper: analyze label bodies from raw .rpy files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models import ProjectModel

logger = logging.getLogger("renpy_analyzer.checks._label_body")

RE_LABEL = re.compile(r"^(\s*)label\s+(\w+)\s*(?:\(.*\))?\s*:")
RE_RETURN = re.compile(r"^\s+return\b")
RE_JUMP = re.compile(r"^\s+jump\s+(\w+)")
RE_TOP_LEVEL = re.compile(r"^(?:label|init|screen|transform|define|default|style|python|image)\b")


@dataclass
class LabelBody:
    name: str
    file: str
    line: int
    body_lines: int = 0
    has_return: bool = False
    ends_with_jump: bool = False
    only_pass: bool = False
    jump_targets: list[str] = field(default_factory=list)


def analyze_label_bodies(project: ProjectModel) -> dict[str, LabelBody]:
    """Map label name -> LabelBody for all labels in the project.

    Reads raw files (like flow.py). When duplicate labels exist,
    keeps the first occurrence.
    """
    result: dict[str, LabelBody] = {}
    root = Path(project.root_dir)

    for file_path_str in project.files:
        file_path = Path(file_path_str)
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            logger.warning("Could not read %s: %s", file_path_str, exc)
            continue

        if file_path.is_absolute():
            rel_path = str(file_path.relative_to(root))
        else:
            rel_path = file_path_str

        _analyze_file(lines, rel_path, result)

    return result


def _analyze_file(lines: list[str], rel_path: str, result: dict[str, LabelBody]) -> None:
    # First pass: find all label positions
    label_positions: list[tuple[int, str, int]] = []  # (line_idx, name, indent_len)
    for i, raw_line in enumerate(lines):
        m = RE_LABEL.match(raw_line)
        if m:
            label_positions.append((i, m.group(2), len(m.group(1))))

    # Second pass: analyze each label body
    for idx, (start_idx, name, label_indent) in enumerate(label_positions):
        if name in result:
            continue  # keep first occurrence

        # Determine body range: from line after label to next label/top-level/EOF
        body_start = start_idx + 1
        if idx + 1 < len(label_positions):
            body_end = label_positions[idx + 1][0]
        else:
            body_end = len(lines)

        # Analyze body
        body = LabelBody(name=name, file=rel_path, line=start_idx + 1)
        meaningful_lines = 0
        last_meaningful_is_jump = False
        all_pass = True

        for j in range(body_start, body_end):
            raw = lines[j]
            stripped = raw.strip()

            # Skip blank lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Check if this line is at or before label indent (body ended)
            line_indent = len(raw) - len(raw.lstrip())
            if line_indent <= label_indent and RE_TOP_LEVEL.match(stripped):
                break

            meaningful_lines += 1

            if stripped != "pass":
                all_pass = False

            if RE_RETURN.match(raw):
                body.has_return = True

            m_jump = RE_JUMP.match(raw)
            if m_jump:
                body.jump_targets.append(m_jump.group(1))
                last_meaningful_is_jump = True
            else:
                last_meaningful_is_jump = False

        body.body_lines = meaningful_lines
        body.ends_with_jump = last_meaningful_is_jump
        body.only_pass = (meaningful_lines > 0 and all_pass)

        result[name] = body
