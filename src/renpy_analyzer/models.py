"""Data models for parsed Ren'Py project elements."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    """Finding severity levels, ordered from most to least severe."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    STYLE = 4


@dataclass
class Label:
    name: str
    file: str
    line: int


@dataclass
class Jump:
    target: str
    file: str
    line: int


@dataclass
class Call:
    target: str
    file: str
    line: int


@dataclass
class DynamicJump:
    expression: str
    file: str
    line: int


@dataclass
class Variable:
    name: str
    file: str
    line: int
    kind: str  # "default", "define", "assign", "augment"
    value: str | None = None


@dataclass
class MenuChoice:
    text: str
    line: int
    content_lines: int
    has_jump: bool
    has_return: bool
    condition: str | None = None


@dataclass
class Menu:
    file: str
    line: int
    choices: list[MenuChoice] = field(default_factory=list)


@dataclass
class SceneRef:
    image_name: str
    file: str
    line: int
    transition: str | None = None


@dataclass
class ShowRef:
    image_name: str
    file: str
    line: int


@dataclass
class ImageDef:
    name: str
    file: str
    line: int
    value: str | None = None


@dataclass
class MusicRef:
    path: str
    file: str
    line: int
    action: str  # "play", "stop", "sound", "voice", "audio", "queue"


@dataclass
class CharacterDef:
    shorthand: str
    display_name: str
    file: str
    line: int


@dataclass
class DialogueLine:
    speaker: str
    file: str
    line: int
    text: str = ""


@dataclass
class ScreenDef:
    name: str
    file: str
    line: int


@dataclass
class ScreenRef:
    name: str
    file: str
    line: int
    action: str  # "show", "call", "hide"


@dataclass
class TransformDef:
    name: str
    file: str
    line: int


@dataclass
class TransformRef:
    name: str
    file: str
    line: int


@dataclass
class TranslationBlock:
    language: str
    string_id: str
    file: str
    line: int


@dataclass
class Condition:
    expression: str
    file: str
    line: int


@dataclass
class Finding:
    severity: Severity
    check_name: str
    title: str
    description: str
    file: str
    line: int
    suggestion: str = ""


@dataclass
class ProjectModel:
    """Aggregated data from all parsed .rpy files in a project."""

    root_dir: str
    files: list[str] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    jumps: list[Jump] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    dynamic_jumps: list[DynamicJump] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    menus: list[Menu] = field(default_factory=list)
    scenes: list[SceneRef] = field(default_factory=list)
    shows: list[ShowRef] = field(default_factory=list)
    images: list[ImageDef] = field(default_factory=list)
    music: list[MusicRef] = field(default_factory=list)
    characters: list[CharacterDef] = field(default_factory=list)
    dialogue: list[DialogueLine] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)
    screen_defs: list[ScreenDef] = field(default_factory=list)
    screen_refs: list[ScreenRef] = field(default_factory=list)
    transform_defs: list[TransformDef] = field(default_factory=list)
    transform_refs: list[TransformRef] = field(default_factory=list)
    translations: list[TranslationBlock] = field(default_factory=list)
    has_rpa: bool = False
    has_rpyc_only: bool = False
