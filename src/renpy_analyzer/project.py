"""Project loader: discovers .rpy files and builds the full ProjectModel."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import ProjectModel
from .parser import parse_file

logger = logging.getLogger("renpy_analyzer.project")

# All model list keys — must match ProjectModel fields
_MODEL_KEYS = [
    "labels",
    "jumps",
    "calls",
    "dynamic_jumps",
    "variables",
    "menus",
    "scenes",
    "shows",
    "images",
    "music",
    "characters",
    "dialogue",
    "conditions",
    "screen_defs",
    "screen_refs",
    "transform_defs",
    "transform_refs",
    "translations",
]


def load_project(path: str, sdk_path: str | None = None) -> ProjectModel:
    """Load a Ren'Py project from a directory path.

    If path points to a directory containing a 'game/' subfolder,
    uses the game/ subfolder. Otherwise scans the directory directly.

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

    rpy_files = sorted(scan_dir.rglob("*.rpy"))
    model = ProjectModel(root_dir=str(scan_dir))
    model.files = [str(f) for f in rpy_files]

    if sdk_path:
        _load_with_sdk(model, rpy_files, scan_dir, sdk_path)
    else:
        _load_with_regex(model, rpy_files, scan_dir)

    logger.info("Loaded %d .rpy files from %s", len(rpy_files), scan_dir)
    return model


def _load_with_regex(model: ProjectModel, rpy_files: list[Path], scan_dir: Path) -> None:
    """Parse files using the built-in regex parser."""
    for rpy_file in rpy_files:
        try:
            result = parse_file(str(rpy_file))
        except Exception:
            logger.warning("Skipping %s: failed to parse", rpy_file, exc_info=True)
            continue
        _merge_result(model, result, rpy_file, scan_dir)


def _load_with_sdk(model: ProjectModel, rpy_files: list[Path], scan_dir: Path, sdk_path: str) -> None:
    """Parse files using the Ren'Py SDK's parser via subprocess bridge."""
    from .sdk_bridge import convert_file_result, parse_files_with_sdk

    file_paths = [str(f) for f in rpy_files]
    raw_results = parse_files_with_sdk(file_paths, str(scan_dir), sdk_path)

    for rpy_file in rpy_files:
        file_key = str(rpy_file)
        if file_key not in raw_results:
            logger.warning("SDK parser returned no result for %s", rpy_file)
            continue
        result = convert_file_result(raw_results[file_key], file_key)
        _merge_result(model, result, rpy_file, scan_dir)


def _merge_result(model: ProjectModel, result: dict, rpy_file: Path, scan_dir: Path) -> None:
    """Merge a single file's parse result into the project model."""
    rel_path = str(rpy_file.relative_to(scan_dir))
    for key in result:
        for item in result[key]:
            if hasattr(item, "file"):
                item.file = rel_path

    for key in _MODEL_KEYS:
        getattr(model, key).extend(result[key])
