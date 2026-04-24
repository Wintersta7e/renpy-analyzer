"""Project loader: discovers .rpy files and builds the full ProjectModel."""

from __future__ import annotations

import dataclasses
import logging
import os
import stat
from pathlib import Path

from .models import ProjectModel
from .parser import parse_file

logger = logging.getLogger("renpy_analyzer.project")

# Auto-derive mergeable list fields from ProjectModel dataclass.
# Excludes scalar/dict fields (root_dir, files, has_rpa, has_rpyc_only, raw_lines).
_MODEL_KEYS = [
    f.name
    for f in dataclasses.fields(ProjectModel)
    if f.name not in ("root_dir", "files", "has_rpa", "has_rpyc_only", "raw_lines") and f.default_factory is list
]


def _is_within_root(path: Path, root: Path) -> bool:
    """Return True when ``path`` resolves under ``root``."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _should_descend_into_dir(directory: Path, root_real: Path) -> bool:
    """Return True when a directory is safe to walk."""
    if directory.name == "renpy":
        return False

    try:
        st = directory.lstat()
    except OSError:
        logger.warning("Skipping unreadable directory %s", directory, exc_info=True)
        return False

    if stat.S_ISLNK(st.st_mode):
        logger.warning("Skipping symlinked directory %s", directory)
        return False
    if not stat.S_ISDIR(st.st_mode):
        logger.warning("Skipping non-directory path during walk %s", directory)
        return False

    try:
        resolved = directory.resolve(strict=True)
    except OSError:
        logger.warning("Skipping unresolved directory %s", directory, exc_info=True)
        return False

    if not _is_within_root(resolved, root_real):
        logger.warning("Skipping out-of-root directory %s -> %s", directory, resolved)
        return False

    return True


def _validate_source_file(candidate: Path, root_real: Path, *, label: str) -> Path | None:
    """Return a safe file path or *None* when the candidate is unsafe."""
    try:
        st = candidate.lstat()
    except OSError:
        logger.warning("Skipping unreadable %s %s", label, candidate, exc_info=True)
        return None

    if stat.S_ISLNK(st.st_mode):
        logger.warning("Skipping symlinked %s %s", label, candidate)
        return None
    if not stat.S_ISREG(st.st_mode):
        logger.warning("Skipping non-regular %s %s", label, candidate)
        return None

    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        logger.warning("Skipping unresolved %s %s", label, candidate, exc_info=True)
        return None

    if not _is_within_root(resolved, root_real):
        logger.warning("Skipping out-of-root %s %s -> %s", label, candidate, resolved)
        return None

    return candidate


def _discover_project_files(scan_dir: Path, *, suffix: str, label: str) -> list[Path]:
    """Discover safe project files under ``scan_dir``."""
    root_real = scan_dir.resolve()
    discovered: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(scan_dir, topdown=True, followlinks=False):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if _should_descend_into_dir(current_dir / d, root_real))

        for filename in sorted(filenames):
            if not filename.endswith(suffix):
                continue

            candidate = current_dir / filename
            validated = _validate_source_file(candidate, root_real, label=label)
            if validated is not None:
                discovered.append(validated)

    return discovered


def detect_sub_games(path: str) -> list[str]:
    """Detect multiple sub-game directories within a parent folder.

    Returns a list of sub-directory names that each contain a ``game/``
    folder, or an empty list if the path itself is a single game.
    """
    root = Path(path)
    if (root / "game").is_dir():
        return []  # Single game — no sub-games
    try:
        children = sorted(root.iterdir())
    except OSError:
        logger.warning("Could not list directory: %s", root)
        return []
    sub_games = [child.name for child in children if child.is_dir() and (child / "game").is_dir()]
    return sub_games if len(sub_games) > 1 else []


def load_project(path: str, sdk_path: str | None = None, *, trust_sdk: bool = False) -> ProjectModel:
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
    trust_sdk:
        Explicit opt-in required before executing the SDK parser.
    """
    root = Path(path)
    game_dir = root / "game"
    if game_dir.is_dir():
        scan_dir = game_dir
    else:
        scan_dir = root

    rpy_files = _discover_project_files(scan_dir, suffix=".rpy", label="script file")
    model = ProjectModel(root_dir=str(scan_dir))
    model.files = [str(f) for f in rpy_files]
    model.has_rpa = any(scan_dir.glob("*.rpa"))

    if sdk_path:
        _load_with_sdk(model, rpy_files, scan_dir, sdk_path, trust_sdk=trust_sdk)
    else:
        _load_with_regex(model, rpy_files, scan_dir)

    if not rpy_files:
        rpyc_files = _discover_project_files(scan_dir, suffix=".rpyc", label="compiled script file")
        if rpyc_files:
            model.has_rpyc_only = True

    logger.info("Loaded %d .rpy files from %s", len(rpy_files), scan_dir)
    return model


def _load_with_regex(model: ProjectModel, rpy_files: list[Path], scan_dir: Path) -> None:
    """Parse files using the built-in regex parser."""
    for rpy_file in rpy_files:
        try:
            content = rpy_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            result = parse_file(str(rpy_file), content=content)
        except Exception:
            logger.warning("Skipping %s: failed to parse", rpy_file, exc_info=True)
            continue
        rel_path = str(rpy_file.relative_to(scan_dir))
        model.raw_lines[rel_path] = lines
        _merge_result(model, result, rpy_file, scan_dir)


def _load_with_sdk(
    model: ProjectModel,
    rpy_files: list[Path],
    scan_dir: Path,
    sdk_path: str,
    *,
    trust_sdk: bool,
) -> None:
    """Parse files using the Ren'Py SDK's parser via subprocess bridge."""
    from .sdk_bridge import convert_file_result, parse_files_with_sdk

    file_paths = [str(f) for f in rpy_files]
    raw_results = parse_files_with_sdk(file_paths, str(scan_dir), sdk_path, trust_sdk=trust_sdk)

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
        except OSError as exc:
            logger.warning("Could not read raw lines for %s: %s", rpy_file, exc)
        _merge_result(model, result, rpy_file, scan_dir)

    if sdk_skipped:
        logger.warning(
            "SDK parser skipped %d/%d files",
            sdk_skipped,
            len(rpy_files),
        )


def _merge_result(model: ProjectModel, result: dict, rpy_file: Path, scan_dir: Path) -> None:
    """Merge a single file's parse result into the project model."""
    rel_path = str(rpy_file.relative_to(scan_dir))
    for key in result:
        for item in result[key]:
            if hasattr(item, "file"):
                item.file = rel_path

    for key in _MODEL_KEYS:
        getattr(model, key).extend(result.get(key, []))
