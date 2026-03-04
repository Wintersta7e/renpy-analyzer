"""Check for replay labels missing renpy.end_replay() calls."""

from __future__ import annotations

import re

from ..models import Finding, ProjectModel, Severity
from ._label_body import analyze_label_bodies

RE_REPLAY = re.compile(r"""Replay\(\s*["'](\w+)["']""")


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Scan all raw lines for Replay("label_name") references
    replay_refs: dict[str, tuple[str, int]] = {}  # label -> (file, line)
    for rel_path, lines in project.raw_lines.items():
        for i, raw_line in enumerate(lines):
            m = RE_REPLAY.search(raw_line)
            if m:
                label_name = m.group(1)
                if label_name not in replay_refs:
                    replay_refs[label_name] = (rel_path, i + 1)

    if not replay_refs:
        return findings

    bodies = analyze_label_bodies(project)

    for label_name, (ref_file, ref_line) in replay_refs.items():
        body = bodies.get(label_name)
        if body is None:
            # Label not found — handled by labels check
            continue

        if not body.has_end_replay:
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="replay",
                    title=f"Replay label '{label_name}' missing end_replay()",
                    description=(
                        f"Replay('{label_name}') at {ref_file}:{ref_line} targets a "
                        f"label that never calls renpy.end_replay(). Without this call, "
                        f"the replay never terminates and the game hangs."
                    ),
                    file=body.file,
                    line=body.line,
                    suggestion=f"Add '$ renpy.end_replay()' before the end of label '{label_name}'.",
                )
            )

    return findings
