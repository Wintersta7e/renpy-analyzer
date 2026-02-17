"""Check modules for analyzing Ren'Py projects.

Each module exports a check(project) -> list[Finding] function.
"""

from . import labels, variables, logic, menus, assets, characters

ALL_CHECKS = {
    "Labels": labels.check,
    "Variables": variables.check,
    "Logic": logic.check,
    "Menus": menus.check,
    "Assets": assets.check,
    "Characters": characters.check,
}
