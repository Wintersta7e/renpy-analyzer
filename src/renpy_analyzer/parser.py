"""Regex-based parser for Ren'Py .rpy files."""

from __future__ import annotations

import re
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

# --- Regex patterns ---

RE_LABEL = re.compile(r"^(\s*)label\s+(\w+)\s*:")
RE_JUMP_EXPR = re.compile(r"^\s+jump\s+expression\s+(.+)")
RE_CALL_EXPR = re.compile(r"^\s+call\s+expression\s+(.+)")
RE_JUMP = re.compile(r"^\s+jump\s+(\w+)")
RE_CALL = re.compile(r"^\s+call\s+(\w+)")
RE_DEFAULT = re.compile(r"^\s*default\s+([\w.]+)\s*=\s*(.+)")
RE_DEFINE = re.compile(r"^\s*define\s+([\w.]+)\s*=\s*(.+)")
RE_ASSIGN = re.compile(r"^\s*\$\s+(\w+)\s*=\s*(.+)")
RE_AUGMENT = re.compile(r"^\s*\$\s+(\w+)\s*[+\-*/]=\s*(.+)")
RE_CHARACTER = re.compile(r'^\s*(?:define|default)\s+(\w+)\s*=\s*Character\(\s*"([^"]*)"')
RE_SCENE = re.compile(
    r"^\s+scene\s+([\w]+(?:\s+(?!with\b|at\b|behind\b|onlayer\b|zorder\b|as\b|transform\b)[\w]+)*)(?:\s+with\s+(\w+))?"
)
RE_SHOW = re.compile(r"^\s+show\s+([\w]+(?:\s+(?!with\b|at\b|behind\b|onlayer\b|zorder\b|as\b|transform\b)[\w]+)*)")
RE_IMAGE_ASSIGN = re.compile(r"^image\s+([\w\s]+?)\s*=\s*(.+)")
RE_IMAGE_BLOCK = re.compile(r"^image\s+([\w\s]+?)\s*:")
RE_MUSIC_PLAY = re.compile(r'^\s+play\s+music\s+"([^"]+)"')
RE_MUSIC_STOP = re.compile(r"^\s+stop\s+(music|sound|voice|audio|movie)\b")
RE_SOUND_PLAY = re.compile(r'^\s+play\s+(sound|voice|audio)\s+"([^"]+)"')
RE_MUSIC_QUEUE = re.compile(r'^\s+queue\s+(music|sound|voice|audio)\s+"([^"]+)"')
RE_VOICE_STMT = re.compile(r'^\s+voice\s+"([^"]+)"')
RE_MENU = re.compile(r"^(\s+)menu\s*:")
RE_MENU_CHOICE = re.compile(r'^(\s+)"([^"]+)"(?:\s+if\s+(.+?))?\s*:')
RE_SCREEN_DEF = re.compile(r"^screen\s+(\w+)")
RE_SCREEN_REF = re.compile(r"^\s+(show|call|hide)\s+screen\s+(\w+)")
RE_TRANSFORM_DEF = re.compile(r"^transform\s+(\w+)")
RE_AT_TRANSFORM = re.compile(r"\bat\s+(\w+)")
RE_TRANSLATE = re.compile(r"^translate\s+(\w+)\s+(\w+)\s*:")
RE_DIALOGUE = re.compile(r'^(\s+)(\w+)\s+"((?:[^"\\]|\\.)*)"')
RE_DIALOGUE_FALLBACK = re.compile(r'^(\s+)(\w+)\s+"')
RE_CONDITION = re.compile(r"^\s+(?:if|elif)\s+(.+?)\s*:")
RE_PYTHON_CALL = re.compile(r"^\s*\$\s*\w+\.\w+\s*\(")

RENPY_KEYWORDS = frozenset(
    {
        # Core Ren'Py statements
        "jump",
        "call",
        "return",
        "scene",
        "show",
        "hide",
        "with",
        "play",
        "stop",
        "queue",
        "voice",
        "define",
        "default",
        "init",
        "python",
        "label",
        "menu",
        "if",
        "elif",
        "else",
        "while",
        "for",
        "pass",
        "image",
        "transform",
        "screen",
        "style",
        "translate",
        "pause",
        "nvl",
        "window",
        "camera",
        "at",
        "extend",
        "narrator",
        "rpy",
        # Screen language keywords (can appear as `keyword "string"`)
        "add",
        "text",
        "textbutton",
        "key",
        "use",
        "scrollbars",
        "layout",
        "id",
        "variant",
        "style_prefix",
        "size_group",
        "thumb",
        "color",
        "insensitive_color",
        "font",
        "background",
        "foreground",
    }
)

BUILTIN_IMAGES = frozenset({"black", "text", "vtext"})


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
    dynamic_jumps: list[DynamicJump] = []
    variables: list[Variable] = []
    menus: list[Menu] = []
    scenes: list[SceneRef] = []
    shows: list[ShowRef] = []
    images: list[ImageDef] = []
    music: list[MusicRef] = []
    characters: list[CharacterDef] = []
    dialogue: list[DialogueLine] = []
    conditions: list[Condition] = []
    screen_defs: list[ScreenDef] = []
    screen_refs: list[ScreenRef] = []
    transform_defs: list[TransformDef] = []
    transform_refs: list[TransformRef] = []
    translations: list[TranslationBlock] = []

    menu_stack: list[tuple[Menu, int, MenuChoice | None, int]] = []
    # Each tuple: (menu, menu_indent, current_choice, choice_indent)
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
        # Close any menus whose indent level has been exceeded
        while current_menu is not None and indent <= menu_indent and line.strip() != "":
            if current_choice is not None:
                current_menu.choices.append(current_choice)
                current_choice = None
            menus.append(current_menu)
            if menu_stack:
                current_menu, menu_indent, current_choice, choice_indent = menu_stack.pop()
                # The nested menu block counts as content for the parent choice
                if current_choice is not None:
                    current_choice.content_lines += 1
            else:
                current_menu = None

        if current_menu is not None:
            m = RE_MENU_CHOICE.match(line)
            if m and _get_indent(line) > menu_indent:
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
                choice_indent = _get_indent(line) + (_get_indent(line) - menu_indent)
            elif current_choice is not None and indent >= choice_indent:
                current_choice.content_lines += 1
                stripped = line.strip()
                if stripped.startswith("jump "):
                    current_choice.has_jump = True
                elif stripped == "return":
                    current_choice.has_return = True

        # --- Screen definition (column 0) ---
        m = RE_SCREEN_DEF.match(line)
        if m and indent == 0:
            screen_defs.append(ScreenDef(name=m.group(1), file=display_path, line=lineno))
            continue

        # --- Transform definition (column 0) ---
        m = RE_TRANSFORM_DEF.match(line)
        if m and indent == 0:
            transform_defs.append(TransformDef(name=m.group(1), file=display_path, line=lineno))
            continue

        # --- Translation block (column 0) ---
        m = RE_TRANSLATE.match(line)
        if m and indent == 0:
            translations.append(
                TranslationBlock(
                    language=m.group(1),
                    string_id=m.group(2),
                    file=display_path,
                    line=lineno,
                )
            )
            continue

        # --- Label ---
        m = RE_LABEL.match(line)
        if m:
            labels.append(Label(name=m.group(2), file=display_path, line=lineno))
            continue

        # --- Menu start ---
        m = RE_MENU.match(line)
        if m:
            new_menu_indent = _get_indent(line)
            if current_menu is None:
                menu_indent = new_menu_indent
                current_menu = Menu(file=display_path, line=lineno)
                continue
            elif new_menu_indent > menu_indent:
                # Nested menu — push current menu state onto the stack
                menu_stack.append((current_menu, menu_indent, current_choice, choice_indent))
                menu_indent = new_menu_indent
                current_menu = Menu(file=display_path, line=lineno)
                current_choice = None
                choice_indent = 0
                continue

        # --- Jump expression (before normal jump) ---
        m = RE_JUMP_EXPR.match(line)
        if m:
            dynamic_jumps.append(
                DynamicJump(
                    expression=m.group(1).strip(),
                    file=display_path,
                    line=lineno,
                )
            )
            continue

        # --- Call expression (before normal call) ---
        m = RE_CALL_EXPR.match(line)
        if m:
            dynamic_jumps.append(
                DynamicJump(
                    expression=m.group(1).strip(),
                    file=display_path,
                    line=lineno,
                )
            )
            continue

        # --- Screen reference (must be before Jump/Call/Show) ---
        m = RE_SCREEN_REF.match(line)
        if m:
            screen_refs.append(
                ScreenRef(
                    name=m.group(2),
                    file=display_path,
                    line=lineno,
                    action=m.group(1),
                )
            )
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
            characters.append(
                CharacterDef(
                    shorthand=m.group(1),
                    display_name=m.group(2),
                    file=display_path,
                    line=lineno,
                )
            )
            var_kind = "default" if line.lstrip().startswith("default") else "define"
            variables.append(
                Variable(
                    name=m.group(1),
                    file=display_path,
                    line=lineno,
                    kind=var_kind,
                    value=line.split("=", 1)[1].strip(),
                )
            )
            continue

        # --- Image definition (assignment) ---
        m = RE_IMAGE_ASSIGN.match(line)
        if m:
            images.append(
                ImageDef(
                    name=m.group(1).strip(),
                    file=display_path,
                    line=lineno,
                    value=m.group(2).strip(),
                )
            )
            continue

        # --- Image definition (block) ---
        m = RE_IMAGE_BLOCK.match(line)
        if m:
            images.append(
                ImageDef(
                    name=m.group(1).strip(),
                    file=display_path,
                    line=lineno,
                )
            )
            continue

        # --- Default variable ---
        m = RE_DEFAULT.match(line)
        if m:
            variables.append(
                Variable(
                    name=m.group(1),
                    file=display_path,
                    line=lineno,
                    kind="default",
                    value=m.group(2).strip(),
                )
            )
            continue

        # --- Define (non-character) ---
        m = RE_DEFINE.match(line)
        if m:
            variables.append(
                Variable(
                    name=m.group(1),
                    file=display_path,
                    line=lineno,
                    kind="define",
                    value=m.group(2).strip(),
                )
            )
            continue

        # --- Python augmented assignment ---
        m = RE_AUGMENT.match(line)
        if m:
            variables.append(
                Variable(
                    name=m.group(1),
                    file=display_path,
                    line=lineno,
                    kind="augment",
                )
            )
            continue

        # --- Python assignment (skip function calls) ---
        if RE_PYTHON_CALL.match(line):
            continue

        m = RE_ASSIGN.match(line)
        if m:
            variables.append(
                Variable(
                    name=m.group(1),
                    file=display_path,
                    line=lineno,
                    kind="assign",
                    value=m.group(2).strip(),
                )
            )
            continue

        # --- Scene ---
        m = RE_SCENE.match(line)
        if m:
            scenes.append(
                SceneRef(
                    image_name=m.group(1),
                    file=display_path,
                    line=lineno,
                    transition=m.group(2),
                )
            )
            at_m = RE_AT_TRANSFORM.search(line)
            if at_m:
                transform_refs.append(TransformRef(name=at_m.group(1), file=display_path, line=lineno))
            continue

        # --- Show ---
        m = RE_SHOW.match(line)
        if m:
            shows.append(
                ShowRef(
                    image_name=m.group(1),
                    file=display_path,
                    line=lineno,
                )
            )
            at_m = RE_AT_TRANSFORM.search(line)
            if at_m:
                transform_refs.append(TransformRef(name=at_m.group(1), file=display_path, line=lineno))
            continue

        # --- Music play ---
        m = RE_MUSIC_PLAY.match(line)
        if m:
            music.append(
                MusicRef(
                    path=m.group(1),
                    file=display_path,
                    line=lineno,
                    action="play",
                )
            )
            continue

        # --- Stop music/sound/voice/audio/movie ---
        m = RE_MUSIC_STOP.match(line)
        if m:
            music.append(
                MusicRef(
                    path="",
                    file=display_path,
                    line=lineno,
                    action="stop",
                )
            )
            continue

        # --- Sound/voice/audio play ---
        m = RE_SOUND_PLAY.match(line)
        if m:
            music.append(
                MusicRef(
                    path=m.group(2),
                    file=display_path,
                    line=lineno,
                    action=m.group(1),
                )
            )
            continue

        # --- Queue music/sound/voice/audio ---
        m = RE_MUSIC_QUEUE.match(line)
        if m:
            music.append(
                MusicRef(
                    path=m.group(2),
                    file=display_path,
                    line=lineno,
                    action="queue",
                )
            )
            continue

        # --- Standalone voice statement ---
        m = RE_VOICE_STMT.match(line)
        if m:
            music.append(
                MusicRef(
                    path=m.group(1),
                    file=display_path,
                    line=lineno,
                    action="voice",
                )
            )
            continue

        # --- Condition ---
        m = RE_CONDITION.match(line)
        if m:
            conditions.append(
                Condition(
                    expression=m.group(1),
                    file=display_path,
                    line=lineno,
                )
            )

        # --- Dialogue ---
        m = RE_DIALOGUE.match(line)
        if m:
            speaker = m.group(2)
            if speaker not in RENPY_KEYWORDS:
                dialogue.append(
                    DialogueLine(
                        speaker=speaker,
                        file=display_path,
                        line=lineno,
                        text=m.group(3),
                    )
                )
        else:
            m = RE_DIALOGUE_FALLBACK.match(line)
            if m:
                speaker = m.group(2)
                if speaker not in RENPY_KEYWORDS:
                    dialogue.append(
                        DialogueLine(
                            speaker=speaker,
                            file=display_path,
                            line=lineno,
                        )
                    )

    # Finalize any in-progress menus at end of file (drain the entire stack)
    while current_menu is not None:
        if current_choice is not None:
            current_menu.choices.append(current_choice)
            current_choice = None
        menus.append(current_menu)
        if menu_stack:
            current_menu, menu_indent, current_choice, choice_indent = menu_stack.pop()
            # The nested menu block counts as content for the parent choice
            if current_choice is not None:
                current_choice.content_lines += 1
        else:
            current_menu = None

    return {
        "labels": labels,
        "jumps": jumps,
        "calls": calls,
        "dynamic_jumps": dynamic_jumps,
        "variables": variables,
        "menus": menus,
        "scenes": scenes,
        "shows": shows,
        "images": images,
        "music": music,
        "characters": characters,
        "dialogue": dialogue,
        "conditions": conditions,
        "screen_defs": screen_defs,
        "screen_refs": screen_refs,
        "transform_defs": transform_defs,
        "transform_refs": transform_refs,
        "translations": translations,
    }
