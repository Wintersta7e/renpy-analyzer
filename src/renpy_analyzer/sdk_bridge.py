"""SDK bridge: spawns the Ren'Py SDK's Python to parse files via bridge_worker."""

from __future__ import annotations

import json
import logging
import platform
import stat
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
    ScreenDef,
    ScreenRef,
    ShowRef,
    TransformDef,
    TransformRef,
    TranslationBlock,
    Variable,
)

logger = logging.getLogger("renpy_analyzer.sdk_bridge")

# Timeout for the subprocess (seconds)
_SUBPROCESS_TIMEOUT = 120
_SDK_TRUST_ERROR = (
    "SDK parsing executes the selected SDK's bundled Python interpreter. Only enable it for SDKs you trust."
)


def require_trusted_sdk(sdk_path: str, trust_sdk: bool) -> None:
    """Reject SDK execution unless the caller opted in explicitly."""
    if trust_sdk:
        return
    raise RuntimeError(f"{_SDK_TRUST_ERROR} Refusing to execute SDK at {sdk_path!r}.")


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_has_symlink_component(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True

    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_sdk_dir(directory: Path) -> bool:
    try:
        st = directory.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode)


def _safe_sdk_file(candidate: Path, sdk_root: Path, sdk_root_real: Path) -> bool:
    try:
        st = candidate.lstat()
    except OSError:
        return False

    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return False
    if _path_has_symlink_component(candidate, sdk_root):
        return False

    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return False

    return _is_within_root(resolved, sdk_root_real / "lib")


def find_sdk_python(sdk_path: str) -> str:
    """Locate the SDK's bundled Python binary.

    Raises RuntimeError if not found.
    """
    sdk = Path(sdk_path)
    if not _safe_sdk_dir(sdk):
        raise RuntimeError(f"SDK path must be a real directory, not a symlink or special file: {sdk_path}")

    try:
        sdk_real = sdk.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"Could not resolve SDK path {sdk_path}: {exc}") from exc

    lib_dir = sdk / "lib"
    if lib_dir.exists() and not _safe_sdk_dir(lib_dir):
        raise RuntimeError(f"SDK lib directory must be a real directory, not a symlink: {lib_dir}")

    system = platform.system().lower()

    # Platform-specific search order (try py3 first, then py2 for older SDKs)
    candidates = []
    if system == "linux":
        candidates.append(sdk / "lib" / "py3-linux-x86_64" / "python")
        candidates.append(sdk / "lib" / "py2-linux-x86_64" / "python")
    elif system == "windows":
        candidates.append(sdk / "lib" / "py3-windows-x86_64" / "python.exe")
        candidates.append(sdk / "lib" / "py2-windows-x86_64" / "python.exe")
    elif system == "darwin":
        candidates.append(sdk / "lib" / "py3-mac-universal" / "python")
        candidates.append(sdk / "lib" / "py2-mac-universal" / "python")

    # Fallback: glob for any py3-* or py2-* directory
    for match in sorted(glob(str(sdk / "lib" / "py3-*" / "python*"))):
        p = Path(match)
        if _safe_sdk_file(p, sdk, sdk_real):
            candidates.append(p)
    for match in sorted(glob(str(sdk / "lib" / "py2-*" / "python*"))):
        p = Path(match)
        if _safe_sdk_file(p, sdk, sdk_real):
            candidates.append(p)

    for candidate in candidates:
        if _safe_sdk_file(candidate, sdk, sdk_real):
            logger.debug("Found SDK Python: %s", candidate)
            return str(candidate)

    raise RuntimeError(f"Could not find SDK Python binary in {sdk_path}/lib/. Is this a valid Ren'Py SDK directory?")


def validate_sdk_path(sdk_path: str) -> bool:
    """Quick validation: SDK directory has renpy/ and version is detectable."""
    sdk = Path(sdk_path)
    if not _safe_sdk_dir(sdk):
        return False
    if not _safe_sdk_dir(sdk / "renpy"):
        return False
    if not _safe_sdk_dir(sdk / "lib"):
        return False
    # Must be able to detect the version
    from .version import detect_renpy_version

    if detect_renpy_version(sdk_path) is None:
        return False

    try:
        find_sdk_python(sdk_path)
    except RuntimeError:
        return False
    return True


def detect_sdk_version(sdk_path: str) -> str | None:
    """Detect the Ren'Py version of an SDK and return a formatted string.

    Returns e.g. ``"8.5.2"`` or ``"7.4.10"``, or *None* if detection fails.
    """
    from .version import detect_renpy_version, format_version

    ver = detect_renpy_version(sdk_path)
    if ver is None:
        return None
    return format_version(ver)


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
    *,
    trust_sdk: bool = False,
) -> dict[str, dict]:
    """Parse .rpy files using the SDK's parser via subprocess.

    Returns a dict mapping filepath → parsed element dicts (same format
    as parser.parse_file but with raw dicts instead of dataclasses).

    Raises RuntimeError on subprocess or protocol errors.
    """
    require_trusted_sdk(sdk_path, trust_sdk)
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
        proc = subprocess.run(  # noqa: S603 — args are controlled (SDK python + our worker script)
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

    def _labels() -> list[Label]:
        return [Label(name=d["name"], file=rel_path, line=d["line"]) for d in data.get("labels", [])]

    def _jumps() -> list[Jump]:
        return [Jump(target=d["target"], file=rel_path, line=d["line"]) for d in data.get("jumps", [])]

    def _calls() -> list[Call]:
        return [Call(target=d["target"], file=rel_path, line=d["line"]) for d in data.get("calls", [])]

    def _dynamic_jumps() -> list[DynamicJump]:
        return [
            DynamicJump(expression=d["expression"], file=rel_path, line=d["line"])
            for d in data.get("dynamic_jumps", [])
        ]

    def _variables() -> list[Variable]:
        return [
            Variable(
                name=d["name"],
                file=rel_path,
                line=d["line"],
                kind=d.get("kind", "assign"),
                value=d.get("value"),
                in_init=d.get("in_init", False),
            )
            for d in data.get("variables", [])
        ]

    def _menus() -> list[Menu]:
        menus: list[Menu] = []
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

    def _scenes() -> list[SceneRef]:
        return [
            SceneRef(
                image_name=d["image_name"],
                file=rel_path,
                line=d["line"],
                transition=d.get("transition"),
            )
            for d in data.get("scenes", [])
        ]

    def _shows() -> list[ShowRef]:
        return [ShowRef(image_name=d["image_name"], file=rel_path, line=d["line"]) for d in data.get("shows", [])]

    def _images() -> list[ImageDef]:
        return [
            ImageDef(
                name=d["name"],
                file=rel_path,
                line=d["line"],
                value=d.get("value"),
            )
            for d in data.get("images", [])
        ]

    def _music() -> list[MusicRef]:
        return [
            MusicRef(
                path=d["path"],
                file=rel_path,
                line=d["line"],
                action=d.get("action", "play"),
            )
            for d in data.get("music", [])
        ]

    def _characters() -> list[CharacterDef]:
        return [
            CharacterDef(
                shorthand=d["shorthand"],
                display_name=d["display_name"],
                file=rel_path,
                line=d["line"],
            )
            for d in data.get("characters", [])
        ]

    def _dialogue() -> list[DialogueLine]:
        return [
            DialogueLine(speaker=d["speaker"], file=rel_path, line=d["line"], text=d.get("text", ""))
            for d in data.get("dialogue", [])
        ]

    def _conditions() -> list[Condition]:
        return [
            Condition(expression=d["expression"], file=rel_path, line=d["line"]) for d in data.get("conditions", [])
        ]

    def _screen_defs() -> list[ScreenDef]:
        return [ScreenDef(name=d["name"], file=rel_path, line=d["line"]) for d in data.get("screen_defs", [])]

    def _screen_refs() -> list[ScreenRef]:
        return [
            ScreenRef(name=d["name"], file=rel_path, line=d["line"], action=d.get("action", "show"))
            for d in data.get("screen_refs", [])
        ]

    def _transform_defs() -> list[TransformDef]:
        return [TransformDef(name=d["name"], file=rel_path, line=d["line"]) for d in data.get("transform_defs", [])]

    def _transform_refs() -> list[TransformRef]:
        return [TransformRef(name=d["name"], file=rel_path, line=d["line"]) for d in data.get("transform_refs", [])]

    def _translations() -> list[TranslationBlock]:
        return [
            TranslationBlock(
                language=d["language"],
                string_id=d["string_id"],
                file=rel_path,
                line=d["line"],
            )
            for d in data.get("translations", [])
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
        "screen_defs": _screen_defs(),
        "screen_refs": _screen_refs(),
        "transform_defs": _transform_defs(),
        "transform_refs": _transform_refs(),
        "translations": _translations(),
    }
