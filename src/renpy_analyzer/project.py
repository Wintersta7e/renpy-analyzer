"""Project loader: discovers .rpy files and builds the full ProjectModel."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

from .models import ProjectModel
from .parser import parse_file

logger = logging.getLogger("renpy_analyzer.project")

# Auto-derive mergeable list fields from ProjectModel dataclass.
# Excludes scalar/dict fields (root_dir, files, has_rpa, has_rpyc_only, raw_lines).
_MODEL_KEYS = [
    f.name
    for f in dataclasses.fields(ProjectModel)
    if f.name not in ("root_dir", "files", "has_rpa", "has_rpyc_only", "raw_lines")
    and f.default_factory is list
]


def _is_engine_file(path: Path) -> bool:
    """Return True if the file is a Ren'Py engine file (not user code).

    Engine files live under a 'renpy/' directory that ships with every
    Ren'Py game.  These contain engine internals (common screens, default
    persistent vars, ATL, etc.) that the game developer did not write and
    cannot control.  Scanning them produces false positives across all
    checks.
    """
    parts = path.parts
    return "renpy" in parts


def detect_sub_games(path: str) -> list[str]:
    """Detect multiple sub-game directories within a parent folder.

    Returns a list of sub-directory names that each contain a ``game/``
    folder, or an empty list if the path itself is a single game.
    """
    root = Path(path)
    if (root / "game").is_dir():
        return []  # Single game — no sub-games
    sub_games = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "game").is_dir():
            sub_games.append(child.name)
    return sub_games if len(sub_games) > 1 else []


def load_project(path: str, sdk_path: str | None = None) -> ProjectModel:
    """Load a Ren'Py project from a directory path.

    If path points to a directory containing a 'game/' subfolder,
    uses the game/ subfolder. Otherwise scans the directory directly.

    For directories with multiple sub-games, use :func:`detect_sub_games`
    and call this function once per sub-game.

    Parameters
    ----------
    path:
        Path to the Ren'Py project root.
    sdk_path:
        Optional path to a Ren'Py SDK directory. When provided, uses
        the SDK's parser via subprocess instead of the regex parser.
    """
    root = Path(path)
    game_dir = root / "game"
    if game_dir.is_dir():
        scan_dir = game_dir
    else:
        scan_dir = root

    rpy_files = sorted(
        f for f in scan_dir.rglob("*.rpy")
        if not _is_engine_file(f)
    )
    model = ProjectModel(root_dir=str(scan_dir))
    model.files = [str(f) for f in rpy_files]
    model.has_rpa = any(scan_dir.glob("*.rpa"))

    if sdk_path:
        _load_with_sdk(model, rpy_files, scan_dir, sdk_path)
    else:
        _load_with_regex(model, rpy_files, scan_dir)

    if not rpy_files:
        rpyc_files = list(scan_dir.rglob("*.rpyc"))
        if rpyc_files:
            model.has_rpyc_only = True

    logger.info("Loaded %d .rpy files from %s", len(rpy_files), scan_dir)
    return model


def _load_with_regex(model: ProjectModel, rpy_files: list[Path], scan_dir: Path) -> None:
    """Parse files using the built-in regex parser."""
    for rpy_file in rpy_files:
        try:
            lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            result = parse_file(str(rpy_file))
        except Exception:
            logger.warning("Skipping %s: failed to parse", rpy_file, exc_info=True)
            continue
        rel_path = str(rpy_file.relative_to(scan_dir))
        model.raw_lines[rel_path] = lines
        _merge_result(model, result, rpy_file, scan_dir)


def _load_with_sdk(model: ProjectModel, rpy_files: list[Path], scan_dir: Path, sdk_path: str) -> None:
    """Parse files using the Ren'Py SDK's parser via subprocess bridge."""
    from .sdk_bridge import convert_file_result, parse_files_with_sdk

    file_paths = [str(f) for f in rpy_files]
    raw_results = parse_files_with_sdk(file_paths, str(scan_dir), sdk_path)

    sdk_skipped = 0
    for rpy_file in rpy_files:
        file_key = str(rpy_file)
        if file_key not in raw_results:
            sdk_skipped += 1
            logger.warning("SDK parser skipped %s — file not in results", rpy_file)
            continue
        result = convert_file_result(raw_results[file_key], file_key)
        try:
            lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            rel_path = str(rpy_file.relative_to(scan_dir))
            model.raw_lines[rel_path] = lines
        except OSError:
            pass
        _merge_result(model, result, rpy_file, scan_dir)

    if sdk_skipped:
        logger.warning(
            "SDK parser skipped %d/%d files",
            sdk_skipped, len(rpy_files),
        )


def _merge_result(model: ProjectModel, result: dict, rpy_file: Path, scan_dir: Path) -> None:
    """Merge a single file's parse result into the project model."""
    rel_path = str(rpy_file.relative_to(scan_dir))
    for key in result:
        for item in result[key]:
            if hasattr(item, "file"):
                item.file = rel_path

    for key in _MODEL_KEYS:
        getattr(model, key).extend(result[key])
