"""Persistent settings for Ren'Py Analyzer — JSON file via platformdirs."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import platformdirs

logger = logging.getLogger("renpy_analyzer.settings")

_APP_NAME = "renpy-analyzer"
_SETTINGS_FILE = "settings.json"

# Fields that Settings.__init__ accepts (used to filter unknown keys)
_KNOWN_FIELDS = frozenset({
    "sdk_paths",
    "game_path",
    "window_geometry",
    "check_toggles",
    "severity_filters",
    "sort_column",
    "sort_ascending",
})

# Expected types for each field — used to reject wrong-typed values from JSON
_FIELD_TYPES: dict[str, type] = {
    "sdk_paths": list,
    "game_path": str,
    "window_geometry": str,
    "check_toggles": dict,
    "severity_filters": dict,
    "sort_column": str,
    "sort_ascending": bool,
}


def _config_path() -> Path:
    """Return the platform-appropriate config directory."""
    return Path(platformdirs.user_config_dir(_APP_NAME))


@dataclass
class Settings:
    """User-persistent settings stored as JSON."""

    sdk_paths: list[str] = field(default_factory=list)
    game_path: str = ""
    window_geometry: str = "1050x780"
    check_toggles: dict[str, bool] = field(default_factory=dict)
    severity_filters: dict[str, bool] = field(default_factory=dict)
    sort_column: str = "severity"
    sort_ascending: bool = True

    def save(self) -> None:
        """Write settings to disk atomically.  Logs warnings on failure."""
        try:
            config_dir = _config_path()
            config_dir.mkdir(parents=True, exist_ok=True)
            filepath = config_dir / _SETTINGS_FILE
            payload = json.dumps(asdict(self), indent=2, ensure_ascii=False)
            # Atomic write: temp file in same dir, then rename
            fd, tmp = tempfile.mkstemp(dir=config_dir, prefix=".settings-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, filepath)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError as exc:
            logger.warning("Failed to save settings: %s", exc)
        except Exception:
            logger.warning("Unexpected error saving settings", exc_info=True)

    @classmethod
    def load(cls) -> Settings:
        """Load settings from disk.  Returns defaults on any failure.

        Handles migration from the old ``sdk_path`` (string) field to the
        new ``sdk_paths`` (list) field automatically.
        """
        try:
            filepath = _config_path() / _SETTINGS_FILE
            if not filepath.exists():
                return cls()
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning("Settings file has invalid format, using defaults")
                return cls()

            # --- Migration: old sdk_path (str) → sdk_paths (list) ---
            if "sdk_path" in data and "sdk_paths" not in data:
                old_val = data.pop("sdk_path")
                if isinstance(old_val, str) and old_val:
                    data["sdk_paths"] = [old_val]
                    logger.info("Migrated sdk_path → sdk_paths: %s", old_val)
                else:
                    data["sdk_paths"] = []
            elif "sdk_path" in data:
                # Both keys present — drop the old one
                data.pop("sdk_path")

            # Filter to known fields with correct types (forward-compatible)
            filtered: dict[str, object] = {}
            for k, v in data.items():
                if k in _KNOWN_FIELDS:
                    expected = _FIELD_TYPES[k]
                    # bool is subclass of int in Python — require exact bool for bool fields
                    if expected is bool:
                        if type(v) is bool:
                            filtered[k] = v
                    elif isinstance(v, expected):
                        # For sdk_paths, validate that all elements are strings
                        if k == "sdk_paths" and isinstance(v, list):
                            filtered[k] = [s for s in v if isinstance(s, str)]
                        else:
                            filtered[k] = v
            return cls(**filtered)  # type: ignore[arg-type]
        except json.JSONDecodeError:
            logger.warning("Settings file is corrupted, using defaults: %s", _config_path() / _SETTINGS_FILE)
            return cls()
        except OSError as exc:
            logger.warning("Cannot read settings file: %s", exc)
            return cls()
        except Exception:
            logger.warning("Unexpected error loading settings", exc_info=True)
            return cls()
