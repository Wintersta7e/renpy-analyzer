"""Check for NVL mode overflow: too many lines without nvl clear."""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity

RE_NVL_CHARACTER = re.compile(r"""Character\([^)]*kind\s*=\s*nvl\b""")
RE_NVL_CLEAR = re.compile(r"^\s+nvl\s+clear\b")
RE_DIALOGUE = re.compile(r"^\s+(\w+)\s+\"")
RE_NARRATOR = re.compile(r"^\s+\"")
RE_LABEL = re.compile(r"^(\s*)label\s+\w+")
RE_SCENE = re.compile(r"^\s+scene\s+")

# Threshold before warning — most NVL screens fit ~8-12 lines comfortably
NVL_LINE_THRESHOLD = 15


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Identify NVL character shorthands from variable definitions
    nvl_speakers: set[str] = set()
    for var in project.variables:
        if var.kind in ("define", "default") and var.value and RE_NVL_CHARACTER.search(var.value):
            nvl_speakers.add(var.name)

    if not nvl_speakers:
        return findings

    # Scan raw files for NVL dialogue runs without nvl clear
    for rel_path, lines in project.raw_lines.items():
        nvl_run_start: int | None = None
        nvl_count = 0

        for i, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # nvl clear or scene change resets the accumulator
            if RE_NVL_CLEAR.match(raw_line) or RE_SCENE.match(raw_line):
                nvl_run_start = None
                nvl_count = 0
                continue

            # Label boundary resets
            if RE_LABEL.match(raw_line):
                nvl_run_start = None
                nvl_count = 0
                continue

            # Check if this is dialogue from an NVL speaker
            m = RE_DIALOGUE.match(raw_line)
            if m and m.group(1) in nvl_speakers:
                if nvl_run_start is None:
                    nvl_run_start = i + 1
                nvl_count += 1

                if nvl_count == NVL_LINE_THRESHOLD:
                    findings.append(
                        Finding(
                            severity=Severity.MEDIUM,
                            check_name="nvl",
                            title=f"NVL overflow ({nvl_count}+ lines without clear)",
                            description=(
                                f"NVL dialogue starting at {rel_path}:{nvl_run_start} has "
                                f"{nvl_count}+ lines without an 'nvl clear'. Lines will "
                                f"overflow off the bottom of the NVL text window."
                            ),
                            file=rel_path,
                            line=nvl_run_start,
                            suggestion="Add 'nvl clear' to break the text into pages.",
                        )
                    )

    return findings
