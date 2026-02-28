"""Ren'Py version detection for games and SDKs."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("renpy_analyzer.version")

# Matches: version = '8.5.2.26010301'  or  version = u'7.8.7.25031702'
_RE_VC_VERSION_STR = re.compile(r"""^version\s*=\s*u?['"](\d+\.\d+\.\d+)""", re.MULTILINE)

# Matches: version_tuple = (7, 4, 10, vc_version)  (__init__.py in 7.x)
_RE_VERSION_TUPLE = re.compile(r"version_tuple\s*=\s*\((\d+),\s*(\d+),\s*(\d+)")


def detect_renpy_version(path: str) -> tuple[int, ...] | None:
    """Detect the Ren'Py version at the given path.

    Checks for ``renpy/vc_version.py`` (8.x+ format with version string)
    and ``renpy/__init__.py`` (7.x format with version_tuple literal).

    Works for both game directories and SDK directories. For game dirs,
    also checks ``<path>/game/renpy/``.

    Returns a tuple like ``(8, 5, 2)`` or ``(7, 4, 10)`` or *None* if
    version cannot be determined.
    """
    root = Path(path)

    # Candidate renpy/ directories: direct child, or inside game/
    candidates = [root / "renpy", root / "game" / "renpy"]

    for renpy_dir in candidates:
        if not renpy_dir.is_dir():
            continue

        # Try vc_version.py first (8.x+ has version = '8.5.2.xxx')
        vc_file = renpy_dir / "vc_version.py"
        if vc_file.is_file():
            ver = _parse_vc_version(vc_file)
            if ver:
                return ver

        # Fall back to __init__.py (7.x has version_tuple = (7, 4, 10, ...))
        init_file = renpy_dir / "__init__.py"
        if init_file.is_file():
            ver = _parse_init_version(init_file)
            if ver:
                return ver

    return None


def _parse_vc_version(filepath: Path) -> tuple[int, ...] | None:
    """Parse version from vc_version.py (8.x+ format)."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = _RE_VC_VERSION_STR.search(text)
    if m:
        parts = tuple(int(x) for x in m.group(1).split("."))
        logger.debug("Detected version %s from %s", parts, filepath)
        return parts
    return None


def _parse_init_version(filepath: Path) -> tuple[int, ...] | None:
    """Parse version_tuple from __init__.py (7.x format)."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = _RE_VERSION_TUPLE.search(text)
    if m:
        parts = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        logger.debug("Detected version %s from %s", parts, filepath)
        return parts
    return None


def format_version(ver: tuple[int, ...]) -> str:
    """Format a version tuple as a dotted string, e.g. ``(7, 5, 3)`` → ``'7.5.3'``."""
    return ".".join(str(x) for x in ver)


def select_sdk(
    game_version: tuple[int, ...] | None,
    sdk_paths: list[str],
) -> str | None:
    """Select the best SDK for a game version from a list of SDK paths.

    Matches by major version (e.g. game 7.x → SDK 7.x, game 8.x → SDK 8.x).
    If multiple SDKs share the same major version, picks the one with the
    highest minor/patch version.

    Returns the chosen SDK path or *None* if no match found.
    """
    if not game_version or not sdk_paths:
        return None

    game_major = game_version[0]
    best_path: str | None = None
    best_ver: tuple[int, ...] = ()

    for sdk_path in sdk_paths:
        sdk_ver = detect_renpy_version(sdk_path)
        if sdk_ver is None:
            continue
        if sdk_ver[0] != game_major:
            continue
        if sdk_ver > best_ver:
            best_ver = sdk_ver
            best_path = sdk_path

    if best_path:
        logger.info(
            "Selected SDK %s (v%s) for game v%s",
            best_path,
            format_version(best_ver),
            format_version(game_version),
        )
    else:
        logger.info(
            "No SDK with major version %d available for game v%s",
            game_major,
            format_version(game_version),
        )

    return best_path
