"""Project loader: discovers .rpy files and builds the full ProjectModel."""

from __future__ import annotations
from pathlib import Path

from .models import ProjectModel
from .parser import parse_file


def load_project(path: str) -> ProjectModel:
    """Load a Ren'Py project from a directory path.

    If path points to a directory containing a 'game/' subfolder,
    uses the game/ subfolder. Otherwise scans the directory directly.
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

    for rpy_file in rpy_files:
        result = parse_file(str(rpy_file))
        rel_path = str(rpy_file.relative_to(scan_dir))
        for key in result:
            for item in result[key]:
                if hasattr(item, "file"):
                    item.file = rel_path

        model.labels.extend(result["labels"])
        model.jumps.extend(result["jumps"])
        model.calls.extend(result["calls"])
        model.variables.extend(result["variables"])
        model.menus.extend(result["menus"])
        model.scenes.extend(result["scenes"])
        model.shows.extend(result["shows"])
        model.images.extend(result["images"])
        model.music.extend(result["music"])
        model.characters.extend(result["characters"])
        model.dialogue.extend(result["dialogue"])
        model.conditions.extend(result["conditions"])

    return model
