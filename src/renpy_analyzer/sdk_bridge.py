"""SDK bridge: spawns the Ren'Py SDK's Python to parse files via bridge_worker."""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import sys
from glob import glob
from pathlib import Path

from .models import (
    Call,
    CharacterDef,
    Condition,
    DialogueLine,
    DynamicJump,
    ImageDef,
    Jump,
    Label,
    Menu,
    MenuChoice,
    MusicRef,
    SceneRef,
    ShowRef,
    Variable,
)

logger = logging.getLogger("renpy_analyzer.sdk_bridge")

# Timeout for the subprocess (seconds)
_SUBPROCESS_TIMEOUT = 120


def find_sdk_python(sdk_path: str) -> str:
    """Locate the SDK's bundled Python binary.

    Raises RuntimeError if not found.
    """
    sdk = Path(sdk_path)
    system = platform.system().lower()

    # Platform-specific search order
    candidates = []
    if system == "linux":
        candidates.append(sdk / "lib" / "py3-linux-x86_64" / "python")
    elif system == "windows":
        candidates.append(sdk / "lib" / "py3-windows-x86_64" / "python.exe")
    elif system == "darwin":
        candidates.append(sdk / "lib" / "py3-mac-universal" / "python")

    # Fallback: glob for any py3-* directory
    for match in sorted(glob(str(sdk / "lib" / "py3-*" / "python*"))):
        p = Path(match)
        if p.is_file():
            candidates.append(p)

    for candidate in candidates:
        if candidate.is_file():
            logger.debug("Found SDK Python: %s", candidate)
            return str(candidate)

    raise RuntimeError(
        f"Could not find SDK Python binary in {sdk_path}/lib/py3-*/. Is this a valid Ren'Py SDK directory?"
    )


def validate_sdk_path(sdk_path: str) -> bool:
    """Quick validation: SDK directory has renpy/ and a Python binary."""
    sdk = Path(sdk_path)
    if not sdk.is_dir():
        return False
    if not (sdk / "renpy").is_dir():
        return False
    try:
        find_sdk_python(sdk_path)
        return True
    except RuntimeError:
        return False


def _find_bridge_worker() -> str:
    """Find the bridge_worker.py script.

    When running from source, it's in the same package directory.
    When running from PyInstaller, it's bundled as a data file.
    """
    # Check same directory as this module
    here = Path(__file__).parent
    worker = here / "bridge_worker.py"
    if worker.is_file():
        return str(worker)

    # PyInstaller bundle: check _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        worker = Path(meipass) / "bridge_worker.py"
        if worker.is_file():
            return str(worker)

    raise RuntimeError("Cannot find bridge_worker.py")


def parse_files_with_sdk(
    files: list[str],
    game_dir: str,
    sdk_path: str,
    timeout: int = _SUBPROCESS_TIMEOUT,
) -> dict[str, dict]:
    """Parse .rpy files using the SDK's parser via subprocess.

    Returns a dict mapping filepath → parsed element dicts (same format
    as parser.parse_file but with raw dicts instead of dataclasses).

    Raises RuntimeError on subprocess or protocol errors.
    """
    python_bin = find_sdk_python(sdk_path)
    worker_script = _find_bridge_worker()

    request = {
        "sdk_path": sdk_path,
        "game_dir": game_dir,
        "files": files,
    }

    logger.info(
        "Launching SDK parser: %s %s (%d files)",
        python_bin,
        worker_script,
        len(files),
    )

    # On Windows, prevent a console window from flashing up
    creationflags: int = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

    try:
        proc = subprocess.run(
            [python_bin, worker_script],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"SDK parser timed out after {timeout}s. Try using the regex parser instead.") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to launch SDK Python at {python_bin}: {exc}") from exc

    if proc.stderr:
        for line in proc.stderr.strip().splitlines():
            logger.warning("SDK stderr: %s", line)

    if proc.returncode != 0:
        stderr_excerpt = (proc.stderr or "")[:500]
        raise RuntimeError(f"SDK parser exited with code {proc.returncode}:\n{stderr_excerpt}")

    # Parse JSON response
    try:
        response = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Invalid JSON from SDK parser: {exc}") from exc

    if not response.get("success", False):
        errors = response.get("errors", [])
        msg = "; ".join(e.get("message", "unknown") for e in errors)
        raise RuntimeError(f"SDK parser failed: {msg}")

    version = response.get("version", "unknown")
    logger.info("SDK parser (Ren'Py %s) returned %d file results", version, len(response.get("results", {})))

    # Log per-file errors as warnings (non-fatal)
    for err in response.get("errors", []):
        logger.warning("SDK parse error in %s: %s", err.get("file", "?"), err.get("message", "?"))

    return response.get("results", {})  # type: ignore[no-any-return]


def convert_file_result(data: dict, filepath: str) -> dict:
    """Convert a single file's JSON result to model dataclass instances.

    Returns a dict with the same keys as parser.parse_file().
    """
    rel_path = filepath  # Caller will rewrite to relative path

    def _labels():
        return [Label(name=d["name"], file=rel_path, line=d["line"]) for d in data.get("labels", [])]

    def _jumps():
        return [Jump(target=d["target"], file=rel_path, line=d["line"]) for d in data.get("jumps", [])]

    def _calls():
        return [Call(target=d["target"], file=rel_path, line=d["line"]) for d in data.get("calls", [])]

    def _dynamic_jumps():
        return [
            DynamicJump(expression=d["expression"], file=rel_path, line=d["line"])
            for d in data.get("dynamic_jumps", [])
        ]

    def _variables():
        return [
            Variable(
                name=d["name"],
                file=rel_path,
                line=d["line"],
                kind=d.get("kind", "assign"),
                value=d.get("value"),
            )
            for d in data.get("variables", [])
        ]

    def _menus():
        menus = []
        for m in data.get("menus", []):
            choices = [
                MenuChoice(
                    text=c["text"],
                    line=c["line"],
                    content_lines=c.get("content_lines", 0),
                    has_jump=c.get("has_jump", False),
                    has_return=c.get("has_return", False),
                    condition=c.get("condition"),
                )
                for c in m.get("choices", [])
            ]
            menus.append(Menu(file=rel_path, line=m["line"], choices=choices))
        return menus

    def _scenes():
        return [
            SceneRef(
                image_name=d["image_name"],
                file=rel_path,
                line=d["line"],
                transition=d.get("transition"),
            )
            for d in data.get("scenes", [])
        ]

    def _shows():
        return [ShowRef(image_name=d["image_name"], file=rel_path, line=d["line"]) for d in data.get("shows", [])]

    def _images():
        return [
            ImageDef(
                name=d["name"],
                file=rel_path,
                line=d["line"],
                value=d.get("value"),
            )
            for d in data.get("images", [])
        ]

    def _music():
        return [
            MusicRef(
                path=d["path"],
                file=rel_path,
                line=d["line"],
                action=d.get("action", "play"),
            )
            for d in data.get("music", [])
        ]

    def _characters():
        return [
            CharacterDef(
                shorthand=d["shorthand"],
                display_name=d["display_name"],
                file=rel_path,
                line=d["line"],
            )
            for d in data.get("characters", [])
        ]

    def _dialogue():
        return [DialogueLine(speaker=d["speaker"], file=rel_path, line=d["line"]) for d in data.get("dialogue", [])]

    def _conditions():
        return [
            Condition(expression=d["expression"], file=rel_path, line=d["line"]) for d in data.get("conditions", [])
        ]

    return {
        "labels": _labels(),
        "jumps": _jumps(),
        "calls": _calls(),
        "dynamic_jumps": _dynamic_jumps(),
        "variables": _variables(),
        "menus": _menus(),
        "scenes": _scenes(),
        "shows": _shows(),
        "images": _images(),
        "music": _music(),
        "characters": _characters(),
        "dialogue": _dialogue(),
        "conditions": _conditions(),
    }
