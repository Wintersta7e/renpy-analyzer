"""Regex-based parser for Ren'Py .rpy files."""

from __future__ import annotations
import re
from pathlib import Path

from .models import (
    Label, Jump, Call, Variable, MenuChoice, Menu,
    SceneRef, ShowRef, ImageDef, MusicRef, CharacterDef,
    DialogueLine, Condition,
)

# --- Regex patterns ---

RE_LABEL = re.compile(r"^(\s*)label\s+(\w+)\s*:")
RE_JUMP = re.compile(r"^\s+jump\s+(\w+)\s*$")
RE_CALL = re.compile(r"^\s+call\s+(\w+)")
RE_DEFAULT = re.compile(r"^\s*default\s+([\w.]+)\s*=\s*(.+)")
RE_DEFINE = re.compile(r"^\s*define\s+([\w.]+)\s*=\s*(.+)")
RE_ASSIGN = re.compile(r"^\s*\$\s+(\w+)\s*=\s*(.+)")
RE_AUGMENT = re.compile(r"^\s*\$\s+(\w+)\s*[+\-*/]=\s*(.+)")
RE_CHARACTER = re.compile(r'^\s*define\s+(\w+)\s*=\s*Character\(\s*"([^"]*)"')
RE_SCENE = re.compile(r"^\s+scene\s+(\w+)(?:\s+with\s+(\w+))?")
RE_SHOW = re.compile(r"^\s+show\s+(\w+)")
RE_IMAGE_ASSIGN = re.compile(r"^image\s+([\w\s]+?)\s*=\s*(.+)")
RE_IMAGE_BLOCK = re.compile(r"^image\s+([\w\s]+?)\s*:")
RE_MUSIC_PLAY = re.compile(r'^\s+play\s+music\s+"([^"]+)"')
RE_MUSIC_STOP = re.compile(r"^\s+stop\s+music")
RE_MENU = re.compile(r"^(\s+)menu\s*:")
RE_MENU_CHOICE = re.compile(r'^(\s+)"([^"]+)"(?:\s+if\s+(.+?))?\s*:')
RE_DIALOGUE = re.compile(r'^(\s+)(\w+)\s+"')
RE_CONDITION = re.compile(r"^\s+(?:if|elif)\s+(.+?)\s*:")
RE_PYTHON_CALL = re.compile(r"^\s*\$\s*\w+\.\w+")

RENPY_KEYWORDS = frozenset({
    "jump", "call", "return", "scene", "show", "hide", "with",
    "play", "stop", "queue", "voice", "define", "default", "init",
    "python", "label", "menu", "if", "elif", "else", "while", "for",
    "pass", "image", "transform", "screen", "style", "translate",
    "pause", "nvl", "window", "camera", "at",
})

BUILTIN_IMAGES = frozenset({"black", "white"})


def _get_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def parse_file(filepath: str) -> dict:
    """Parse a single .rpy file and return dict of extracted element lists."""
    path = Path(filepath)
    display_path = path.name

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    labels: list[Label] = []
    jumps: list[Jump] = []
    calls: list[Call] = []
    variables: list[Variable] = []
    menus: list[Menu] = []
    scenes: list[SceneRef] = []
    shows: list[ShowRef] = []
    images: list[ImageDef] = []
    music: list[MusicRef] = []
    characters: list[CharacterDef] = []
    dialogue: list[DialogueLine] = []
    conditions: list[Condition] = []

    current_menu: Menu | None = None
    menu_indent: int = 0
    current_choice: MenuChoice | None = None
    choice_indent: int = 0

    for lineno_0, raw_line in enumerate(lines):
        lineno = lineno_0 + 1
        line = raw_line.rstrip()

        if not line or line.lstrip().startswith("#"):
            continue

        indent = _get_indent(line)

        # --- Menu state tracking ---
        if current_menu is not None:
            if indent <= menu_indent and line.strip() != "":
                if current_choice is not None:
                    current_menu.choices.append(current_choice)
                    current_choice = None
                menus.append(current_menu)
                current_menu = None
            else:
                m = RE_MENU_CHOICE.match(line)
                if m and _get_indent(line) == menu_indent + 4:
                    if current_choice is not None:
                        current_menu.choices.append(current_choice)
                    current_choice = MenuChoice(
                        text=m.group(2),
                        line=lineno,
                        content_lines=0,
                        has_jump=False,
                        has_return=False,
                        condition=m.group(3),
                    )
                    choice_indent = _get_indent(line) + 4
                elif current_choice is not None and indent >= choice_indent:
                    current_choice.content_lines += 1
                    stripped = line.strip()
                    if stripped.startswith("jump "):
                        current_choice.has_jump = True
                    elif stripped == "return":
                        current_choice.has_return = True

        # --- Label ---
        m = RE_LABEL.match(line)
        if m:
            labels.append(Label(name=m.group(2), file=display_path, line=lineno))
            continue

        # --- Menu start ---
        m = RE_MENU.match(line)
        if m and current_menu is None:
            menu_indent = _get_indent(line)
            current_menu = Menu(file=display_path, line=lineno)
            continue

        # --- Jump ---
        m = RE_JUMP.match(line)
        if m:
            jumps.append(Jump(target=m.group(1), file=display_path, line=lineno))
            continue

        # --- Call ---
        m = RE_CALL.match(line)
        if m:
            calls.append(Call(target=m.group(1), file=display_path, line=lineno))
            continue

        # --- Character definition ---
        m = RE_CHARACTER.match(line)
        if m:
            characters.append(CharacterDef(
                shorthand=m.group(1),
                display_name=m.group(2),
                file=display_path,
                line=lineno,
            ))
            variables.append(Variable(
                name=m.group(1), file=display_path, line=lineno,
                kind="define", value=line.split("=", 1)[1].strip(),
            ))
            continue

        # --- Image definition (assignment) ---
        m = RE_IMAGE_ASSIGN.match(line)
        if m:
            images.append(ImageDef(
                name=m.group(1).strip(),
                file=display_path,
                line=lineno,
                value=m.group(2).strip(),
            ))
            continue

        # --- Image definition (block) ---
        m = RE_IMAGE_BLOCK.match(line)
        if m:
            images.append(ImageDef(
                name=m.group(1).strip(),
                file=display_path,
                line=lineno,
            ))
            continue

        # --- Default variable ---
        m = RE_DEFAULT.match(line)
        if m:
            variables.append(Variable(
                name=m.group(1), file=display_path, line=lineno,
                kind="default", value=m.group(2).strip(),
            ))
            continue

        # --- Define (non-character) ---
        m = RE_DEFINE.match(line)
        if m:
            variables.append(Variable(
                name=m.group(1), file=display_path, line=lineno,
                kind="define", value=m.group(2).strip(),
            ))
            continue

        # --- Python augmented assignment ---
        m = RE_AUGMENT.match(line)
        if m:
            variables.append(Variable(
                name=m.group(1), file=display_path, line=lineno,
                kind="augment",
            ))
            continue

        # --- Python assignment (skip function calls) ---
        if RE_PYTHON_CALL.match(line):
            continue

        m = RE_ASSIGN.match(line)
        if m:
            variables.append(Variable(
                name=m.group(1), file=display_path, line=lineno,
                kind="assign", value=m.group(2).strip(),
            ))
            continue

        # --- Scene ---
        m = RE_SCENE.match(line)
        if m:
            scenes.append(SceneRef(
                image_name=m.group(1),
                file=display_path,
                line=lineno,
                transition=m.group(2),
            ))
            continue

        # --- Show ---
        m = RE_SHOW.match(line)
        if m:
            shows.append(ShowRef(
                image_name=m.group(1), file=display_path, line=lineno,
            ))
            continue

        # --- Music play ---
        m = RE_MUSIC_PLAY.match(line)
        if m:
            music.append(MusicRef(
                path=m.group(1), file=display_path, line=lineno, action="play",
            ))
            continue

        # --- Music stop ---
        m = RE_MUSIC_STOP.match(line)
        if m:
            music.append(MusicRef(
                path="", file=display_path, line=lineno, action="stop",
            ))
            continue

        # --- Condition ---
        m = RE_CONDITION.match(line)
        if m:
            conditions.append(Condition(
                expression=m.group(1), file=display_path, line=lineno,
            ))

        # --- Dialogue ---
        m = RE_DIALOGUE.match(line)
        if m:
            speaker = m.group(2)
            if speaker not in RENPY_KEYWORDS:
                dialogue.append(DialogueLine(
                    speaker=speaker, file=display_path, line=lineno,
                ))

    # Finalize any in-progress menu at end of file
    if current_menu is not None:
        if current_choice is not None:
            current_menu.choices.append(current_choice)
        menus.append(current_menu)

    return {
        "labels": labels,
        "jumps": jumps,
        "calls": calls,
        "variables": variables,
        "menus": menus,
        "scenes": scenes,
        "shows": shows,
        "images": images,
        "music": music,
        "characters": characters,
        "dialogue": dialogue,
        "conditions": conditions,
    }
