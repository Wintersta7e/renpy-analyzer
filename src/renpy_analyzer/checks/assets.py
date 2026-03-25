"""Check for asset reference issues: undefined scenes, animation path casing."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..models import BUILTIN_IMAGES, Finding, ProjectModel, Severity

logger = logging.getLogger("renpy_analyzer.checks.assets")


def check(project: ProjectModel) -> list[Finding]:
    _dir_listing_cache.clear()
    findings: list[Finding] = []

    defined_images: set[str] = set()
    for img in project.images:
        defined_images.add(img.name.lower())
        first_word = img.name.split()[0] if " " in img.name else img.name
        defined_images.add(first_word.lower())

    defined_images.update(BUILTIN_IMAGES)

    # Scan game/images/ directory for file-based auto-detected images.
    # Ren'Py registers just the lowercased file stem as the image name
    # (see renpy/common/00images.rpy _scan_images_directory).
    root = Path(project.root_dir)
    images_dir = root / "images"
    if images_dir.is_dir():
        try:
            for img_file in images_dir.rglob("*"):
                if img_file.is_file() and img_file.suffix.lower() in (
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".avif",
                    ".svg",
                ):
                    name = img_file.stem.lower()
                    defined_images.add(name)
        except OSError:
            logger.warning("Cannot scan images directory %s", images_dir, exc_info=True)

    # Skip undefined scene image check when .rpa archives are present —
    # images inside archives are invisible to filesystem checks.
    if not project.has_rpa:
        for scene in project.scenes:
            name_lower = scene.image_name.lower()
            tag = name_lower.split()[0] if " " in name_lower else name_lower
            if name_lower not in defined_images and tag not in defined_images:
                findings.append(
                    Finding(
                        severity=Severity.MEDIUM,
                        check_name="assets",
                        title=f"Undefined scene image '{scene.image_name}'",
                        description=(
                            f"'scene {scene.image_name}' at {scene.file}:{scene.line} "
                            f"references an image that has no 'image' definition in any .rpy file. "
                            f"This may work if a matching file exists in game/images/, but "
                            f"explicit definitions are safer."
                        ),
                        file=scene.file,
                        line=scene.line,
                        suggestion=(
                            f"Add 'image {scene.image_name} = ...' or verify the image file exists in game/images/."
                        ),
                    )
                )

    movie_path_re = re.compile(r'Movie\(\s*play\s*=\s*"([^"]+)"')

    for img in project.images:
        if img.value is None:
            continue
        m = movie_path_re.search(img.value)
        if not m:
            continue
        rel_path = m.group(1).lstrip("/")
        _check_file_reference(root, rel_path, "Animation", img.file, img.line, findings)

    # Check audio file references
    for ref in project.music:
        if ref.action == "stop" or not ref.path:
            continue
        rel_path = ref.path.lstrip("/")
        _check_file_reference(root, rel_path, "Audio", ref.file, ref.line, findings)

    # Check MP3 used for looping music
    _check_mp3_music(project, findings)

    # Check reserved keywords in image tags
    _check_reserved_keywords(project, findings)

    # Check scene expression file paths
    _check_scene_expression_paths(project, findings)

    return findings


# Reserved words that cannot appear as parts of image tag names.
# Using these causes Ren'Py parse errors at game launch.
RESERVED_IMAGE_KEYWORDS = frozenset(
    {
        "at",
        "as",
        "behind",
        "onlayer",
        "zorder",
        "show",
        "scene",
        "hide",
        "with",
        "expression",
        "nopredict",
    }
)

RE_SCENE_EXPR = re.compile(r"""^\s+scene\s+expression\s+["']([^"']+)["']""")


def _check_mp3_music(project: ProjectModel, findings: list[Finding]) -> None:
    """Flag MP3 files used for music — they have audible gaps when looping."""
    for ref in project.music:
        if ref.action not in ("play", "queue"):
            continue
        if ref.path.lower().endswith(".mp3"):
            findings.append(
                Finding(
                    severity=Severity.STYLE,
                    check_name="assets",
                    title="MP3 used for music (audible loop gap)",
                    description=(
                        f"'{ref.path}' at {ref.file}:{ref.line} is an MP3 file. "
                        f"MP3 encoders add silence padding at the start and end of files, "
                        f"causing an audible gap when music loops."
                    ),
                    file=ref.file,
                    line=ref.line,
                    suggestion="Convert to OGG Vorbis or Opus for seamless looping.",
                )
            )


# Cache for directory listings, populated per check() call.
_dir_listing_cache: dict[Path, dict[str, str]] = {}


def _list_dir_cached(directory: Path) -> dict[str, str] | None:
    """Return {lowercase_name: actual_name} for entries in directory, cached."""
    if directory in _dir_listing_cache:
        return _dir_listing_cache[directory]
    try:
        entries = {e.name.lower(): e.name for e in directory.iterdir()}
    except OSError:
        logger.warning("Cannot list directory %s", directory, exc_info=True)
        _dir_listing_cache[directory] = {}
        return None
    _dir_listing_cache[directory] = entries
    return entries


def _check_file_reference(
    root: Path, rel_path: str, file_desc: str, ref_file: str, ref_line: int, findings: list[Finding]
) -> None:
    """Check if a referenced file exists, with case-mismatch detection."""
    full_path = root / rel_path
    if not full_path.exists():
        parent = full_path.parent
        if parent.exists():
            actual_files = _list_dir_cached(parent)
            if actual_files is None:
                return
            expected_name = full_path.name.lower()
            if expected_name in actual_files:
                actual_name = actual_files[expected_name]
                if actual_name != full_path.name:
                    findings.append(
                        Finding(
                            severity=Severity.MEDIUM,
                            check_name="assets",
                            title=f"{file_desc} path case mismatch",
                            description=(
                                f"Reference '{rel_path}' at {ref_file}:{ref_line} "
                                f"has case mismatch — actual file is '{actual_name}'. "
                                f"Works on Windows but fails on Linux/macOS."
                            ),
                            file=ref_file,
                            line=ref_line,
                            suggestion=f"Change path to match actual filename '{actual_name}'.",
                        )
                    )
            else:
                findings.append(
                    Finding(
                        severity=Severity.HIGH,
                        check_name="assets",
                        title=f"Missing {file_desc.lower()} file",
                        description=(f"Reference '{rel_path}' at {ref_file}:{ref_line} — file does not exist."),
                        file=ref_file,
                        line=ref_line,
                        suggestion=f"Check the file path and ensure the {file_desc.lower()} file exists.",
                    )
                )
        else:
            before = len(findings)
            _check_directory_casing(root, rel_path, ref_file, ref_line, findings)
            if len(findings) == before:
                findings.append(
                    Finding(
                        severity=Severity.HIGH,
                        check_name="assets",
                        title=f"Missing {file_desc.lower()} file",
                        description=(
                            f"Reference '{rel_path}' at {ref_file}:{ref_line} "
                            f"— file does not exist (directory not found)."
                        ),
                        file=ref_file,
                        line=ref_line,
                        suggestion=f"Check the file path and ensure the {file_desc.lower()} file exists.",
                    )
                )


def _check_directory_casing(root: Path, rel_path: str, ref_file: str, ref_line: int, findings: list[Finding]) -> None:
    parts = Path(rel_path).parts
    current = root
    for part in parts[:-1]:
        if not current.exists():
            break
        all_entries = _list_dir_cached(current)
        if all_entries is None:
            break
        # Filter to directories only (cache stores all entries)
        entries = {k: v for k, v in all_entries.items() if (current / v).is_dir()}
        if part.lower() in entries and entries[part.lower()] != part:
            actual = entries[part.lower()]
            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    check_name="assets",
                    title="Directory case mismatch",
                    description=(
                        f"Reference at {ref_file}:{ref_line} — "
                        f"path component '{part}' should be '{actual}' "
                        f"(case mismatch). Works on Windows, fails on Linux/macOS."
                    ),
                    file=ref_file,
                    line=ref_line,
                    suggestion=f"Change '{part}' to '{actual}' in the path.",
                )
            )
            current = current / actual
        else:
            current = current / part


def _check_reserved_keywords(project: ProjectModel, findings: list[Finding]) -> None:
    """Flag image defs/refs that contain reserved Ren'Py keywords in the tag."""
    for img in project.images:
        parts = img.name.split()
        bad = [p for p in parts if p.lower() in RESERVED_IMAGE_KEYWORDS]
        if bad:
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="assets",
                    title=f"Reserved keyword in image tag '{img.name}'",
                    description=(
                        f"Image definition at {img.file}:{img.line} contains "
                        f"reserved keyword(s): {', '.join(repr(b) for b in bad)}. "
                        f"Ren'Py will fail to parse this at launch."
                    ),
                    file=img.file,
                    line=img.line,
                    suggestion=f"Rename the image tag to avoid reserved words: {', '.join(bad)}.",
                )
            )

    for scene in project.scenes:
        parts = scene.image_name.split()
        bad = [p for p in parts if p.lower() in RESERVED_IMAGE_KEYWORDS]
        if bad:
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="assets",
                    title=f"Reserved keyword in scene image '{scene.image_name}'",
                    description=(
                        f"'scene {scene.image_name}' at {scene.file}:{scene.line} contains "
                        f"reserved keyword(s): {', '.join(repr(b) for b in bad)}. "
                        f"Ren'Py will fail to parse this."
                    ),
                    file=scene.file,
                    line=scene.line,
                    suggestion=f"Rename the image to avoid reserved words: {', '.join(bad)}.",
                )
            )

    for show in project.shows:
        parts = show.image_name.split()
        bad = [p for p in parts if p.lower() in RESERVED_IMAGE_KEYWORDS]
        if bad:
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    check_name="assets",
                    title=f"Reserved keyword in show image '{show.image_name}'",
                    description=(
                        f"'show {show.image_name}' at {show.file}:{show.line} contains "
                        f"reserved keyword(s): {', '.join(repr(b) for b in bad)}. "
                        f"Ren'Py will fail to parse this."
                    ),
                    file=show.file,
                    line=show.line,
                    suggestion=f"Rename the image to avoid reserved words: {', '.join(bad)}.",
                )
            )


def _check_scene_expression_paths(project: ProjectModel, findings: list[Finding]) -> None:
    """Validate file paths in 'scene expression "..."' statements."""
    if project.has_rpa:
        return
    root = Path(project.root_dir)
    for rel_file, lines in project.raw_lines.items():
        for i, line in enumerate(lines, start=1):
            m = RE_SCENE_EXPR.match(line)
            if not m:
                continue
            rel_path = m.group(1).lstrip("/")
            _check_file_reference(
                root,
                rel_path,
                "Scene expression image",
                rel_file,
                i,
                findings,
            )
