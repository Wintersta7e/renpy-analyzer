"""Check for asset reference issues: undefined scenes, animation path casing."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Finding, ProjectModel, Severity
from ..parser import BUILTIN_IMAGES


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    defined_images: set[str] = set()
    for img in project.images:
        defined_images.add(img.name)
        first_word = img.name.split()[0] if " " in img.name else img.name
        defined_images.add(first_word)

    defined_images.update(BUILTIN_IMAGES)

    # Scan game/images/ directory for file-based auto-detected images
    # Ren'Py auto-registers images from files: game/images/**/name.ext -> image "name"
    root = Path(project.root_dir)
    images_dir = root / "images"
    if images_dir.is_dir():
        for img_file in images_dir.rglob("*"):
            if img_file.is_file() and img_file.suffix.lower() in (
                ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga",
            ):
                defined_images.add(img_file.stem)

    for scene in project.scenes:
        if scene.image_name not in defined_images:
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
        full_path = root / rel_path

        if not full_path.exists():
            parent = full_path.parent
            if parent.exists():
                actual_files = {f.name.lower(): f.name for f in parent.iterdir()}
                expected_name = full_path.name.lower()
                if expected_name in actual_files:
                    actual_name = actual_files[expected_name]
                    if actual_name != full_path.name:
                        findings.append(Finding(
                            severity=Severity.MEDIUM,
                            check_name="assets",
                            title="Animation path case mismatch",
                            description=(
                                f"Image '{img.name}' at {img.file}:{img.line} "
                                f"references '{rel_path}' but the actual filename "
                                f"is '{actual_name}'. This works on Windows but fails "
                                f"on case-sensitive filesystems (Linux/macOS)."
                            ),
                            file=img.file,
                            line=img.line,
                            suggestion="Change the path to match the actual filename.",
                        ))
                else:
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        check_name="assets",
                        title="Missing animation file",
                        description=(
                            f"Image '{img.name}' at {img.file}:{img.line} "
                            f"references '{rel_path}' but no matching file exists."
                        ),
                        file=img.file,
                        line=img.line,
                        suggestion="Check the file path and ensure the animation file exists.",
                    ))
            else:
                _check_directory_casing(root, rel_path, img, findings)

    return findings


def _check_directory_casing(root: Path, rel_path: str, img, findings: list[Finding]):
    parts = Path(rel_path).parts
    current = root
    for part in parts[:-1]:
        if not current.exists():
            break
        entries = {e.name.lower(): e.name for e in current.iterdir() if e.is_dir()}
        if part.lower() in entries and entries[part.lower()] != part:
            actual = entries[part.lower()]
            findings.append(Finding(
                severity=Severity.MEDIUM,
                check_name="assets",
                title="Animation directory case mismatch",
                description=(
                    f"Image '{img.name}' at {img.file}:{img.line} — "
                    f"path component '{part}' should be '{actual}' "
                    f"(case mismatch). Works on Windows, fails on Linux/macOS."
                ),
                file=img.file,
                line=img.line,
                suggestion=f"Change '{part}' to '{actual}' in the path.",
            ))
            current = current / actual
        else:
            current = current / part
