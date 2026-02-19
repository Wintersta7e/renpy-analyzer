"""Check for asset reference issues: undefined scenes, animation path casing."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..models import Finding, ProjectModel, Severity
from ..parser import BUILTIN_IMAGES

logger = logging.getLogger("renpy_analyzer.checks.assets")


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    defined_images: set[str] = set()
    for img in project.images:
        defined_images.add(img.name)
        first_word = img.name.split()[0] if " " in img.name else img.name
        defined_images.add(first_word)

    defined_images.update(BUILTIN_IMAGES)

    # Scan game/images/ directory for file-based auto-detected images
    # Ren'Py auto-registers images from files: game/images/bg/park.png -> image "bg park"
    root = Path(project.root_dir)
    images_dir = root / "images"
    if images_dir.is_dir():
        try:
            for img_file in images_dir.rglob("*"):
                if img_file.is_file() and img_file.suffix.lower() in (
                    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga",
                ):
                    rel = img_file.relative_to(images_dir)
                    name = " ".join(rel.with_suffix("").parts)
                    defined_images.add(name)
                    # Also add just the tag (first word) for tag-based matching
                    first_word = rel.with_suffix("").parts[0] if rel.parts else img_file.stem
                    defined_images.add(first_word)
        except OSError:
            logger.warning("Cannot scan images directory %s", images_dir, exc_info=True)

    for scene in project.scenes:
        tag = scene.image_name.split()[0] if " " in scene.image_name else scene.image_name
        if scene.image_name not in defined_images and tag not in defined_images:
            findings.append(Finding(
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
                    f"Add 'image {scene.image_name} = ...' or verify the image file "
                    f"exists in game/images/."
                ),
            ))

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

    return findings


def _check_file_reference(root: Path, rel_path: str, file_desc: str,
                          ref_file: str, ref_line: int, findings: list[Finding]) -> None:
    """Check if a referenced file exists, with case-mismatch detection."""
    full_path = root / rel_path
    if not full_path.exists():
        parent = full_path.parent
        if parent.exists():
            try:
                actual_files = {f.name.lower(): f.name for f in parent.iterdir()}
            except OSError:
                logger.warning("Cannot list directory %s", parent, exc_info=True)
                return
            expected_name = full_path.name.lower()
            if expected_name in actual_files:
                actual_name = actual_files[expected_name]
                if actual_name != full_path.name:
                    findings.append(Finding(
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
                    ))
            else:
                findings.append(Finding(
                    severity=Severity.HIGH,
                    check_name="assets",
                    title=f"Missing {file_desc.lower()} file",
                    description=(
                        f"Reference '{rel_path}' at {ref_file}:{ref_line} "
                        f"— file does not exist."
                    ),
                    file=ref_file,
                    line=ref_line,
                    suggestion=f"Check the file path and ensure the {file_desc.lower()} file exists.",
                ))
        else:
            before = len(findings)
            _check_directory_casing(root, rel_path, ref_file, ref_line, findings)
            if len(findings) == before:
                findings.append(Finding(
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
                ))


def _check_directory_casing(root: Path, rel_path: str, ref_file: str,
                            ref_line: int, findings: list[Finding]) -> None:
    parts = Path(rel_path).parts
    current = root
    for part in parts[:-1]:
        if not current.exists():
            break
        try:
            entries = {e.name.lower(): e.name for e in current.iterdir() if e.is_dir()}
        except OSError:
            logger.warning("Cannot list directory %s", current, exc_info=True)
            break
        if part.lower() in entries and entries[part.lower()] != part:
            actual = entries[part.lower()]
            findings.append(Finding(
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
            ))
            current = current / actual
        else:
            current = current / part
