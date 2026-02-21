"""Check for circular call cycles that cause infinite recursion."""

from __future__ import annotations

from collections import defaultdict

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    # Build call graph: for each label, what labels does it call?
    # First, sort labels by (file, line) so we can find which label a call belongs to
    labels_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
    label_set: set[str] = set()
    for label in project.labels:
        labels_by_file[label.file].append((label.line, label.name))
        label_set.add(label.name)

    # Sort each file's labels by line number
    for file_labels in labels_by_file.values():
        file_labels.sort()

    # Build call graph
    call_graph: dict[str, set[str]] = defaultdict(set)
    # Track call locations for reporting
    call_locations: dict[tuple[str, str], tuple[str, int]] = {}  # (caller, callee) -> (file, line)

    for call in project.calls:
        target = call.target
        if not target or not target.isidentifier():
            continue
        if target not in label_set:
            continue

        # Find which label this call belongs to
        caller = _find_containing_label(call.file, call.line, labels_by_file)
        if caller is None:
            continue

        call_graph[caller].add(target)
        if (caller, target) not in call_locations:
            call_locations[(caller, target)] = (call.file, call.line)

    # Detect cycles using DFS with coloring
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {name: WHITE for name in label_set}
    parent: dict[str, str | None] = {}
    reported_cycles: set[frozenset[str]] = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        for neighbor in call_graph.get(node, set()):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                # Found a cycle — reconstruct it
                cycle = _reconstruct_cycle(node, neighbor, parent)
                cycle_key = frozenset(cycle)
                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    _report_cycle(cycle, call_locations, findings)
            elif color[neighbor] == WHITE:
                parent[neighbor] = node
                dfs(neighbor)
        color[node] = BLACK

    for label_name in sorted(label_set):
        if color.get(label_name, WHITE) == WHITE:
            parent[label_name] = None
            dfs(label_name)

    return findings


def _find_containing_label(
    file: str, line: int, labels_by_file: dict[str, list[tuple[int, str]]]
) -> str | None:
    """Find the label that contains the given line in the given file."""
    file_labels = labels_by_file.get(file)
    if not file_labels:
        return None

    # Find the label with the largest line <= call line
    containing = None
    for label_line, label_name in file_labels:
        if label_line <= line:
            containing = label_name
        else:
            break

    return containing


def _reconstruct_cycle(
    node: str, back_edge_target: str, parent: dict[str, str | None]
) -> list[str]:
    """Reconstruct the cycle from parent chain."""
    if node == back_edge_target:
        return [node]

    cycle = [node]
    current = parent.get(node)
    while current is not None and current != back_edge_target:
        cycle.append(current)
        current = parent.get(current)
    cycle.append(back_edge_target)
    cycle.reverse()
    return cycle


def _report_cycle(
    cycle: list[str],
    call_locations: dict[tuple[str, str], tuple[str, int]],
    findings: list[Finding],
) -> None:
    """Create a finding for a detected call cycle."""
    if len(cycle) == 1:
        name = cycle[0]
        loc = call_locations.get((name, name))
        file = loc[0] if loc else ""
        line = loc[1] if loc else 0
        findings.append(
            Finding(
                severity=Severity.CRITICAL,
                check_name="callcycle",
                title=f"Self-recursive call cycle: {name}",
                description=(
                    f"Label '{name}' calls itself, creating infinite recursion. "
                    f"This will crash with a stack overflow when the label is reached."
                ),
                file=file,
                line=line,
                suggestion=f"Use a loop or conditional to control recursion in label '{name}'.",
            )
        )
    else:
        cycle_str = " \u2192 ".join(cycle) + " \u2192 " + cycle[0]
        loc = call_locations.get((cycle[0], cycle[1]))
        file = loc[0] if loc else ""
        line = loc[1] if loc else 0
        findings.append(
            Finding(
                severity=Severity.CRITICAL,
                check_name="callcycle",
                title=f"Circular call cycle: {cycle_str}",
                description=(
                    f"Labels form a circular call chain: {cycle_str}. "
                    f"If this cycle is entered, it will cause infinite recursion "
                    f"and crash with a stack overflow."
                ),
                file=file,
                line=line,
                suggestion="Break the cycle by using 'jump' instead of 'call' for at least one link in the chain, or add a conditional guard.",
            )
        )
