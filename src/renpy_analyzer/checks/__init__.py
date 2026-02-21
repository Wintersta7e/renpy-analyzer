"""Check modules for analyzing Ren'Py projects.

Each module exports a check(project) -> list[Finding] function.
"""

from . import (
    assets,
    callcycle,
    callreturn,
    characters,
    emptylabels,
    flow,
    labels,
    logic,
    menus,
    persistent,
    screens,
    texttags,
    transforms,
    translations,
    variables,
)

ALL_CHECKS = {
    "Labels": labels.check,
    "Variables": variables.check,
    "Logic": logic.check,
    "Menus": menus.check,
    "Assets": assets.check,
    "Characters": characters.check,
    "Flow": flow.check,
    "Screens": screens.check,
    "Transforms": transforms.check,
    "Translations": translations.check,
    "Text Tags": texttags.check,
    "Call Safety": callreturn.check,
    "Call Cycles": callcycle.check,
    "Empty Labels": emptylabels.check,
    "Persistent Vars": persistent.check,
}
