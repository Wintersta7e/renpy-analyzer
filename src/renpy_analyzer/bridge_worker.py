#!/usr/bin/env python
"""Bridge worker: runs under the Ren'Py SDK's bundled Python.

Reads a JSON request from stdin, uses the SDK's renpy.parser to parse
.rpy files, walks the AST, and writes a JSON response to stdout.

This file is STANDALONE — it must not import anything from renpy_analyzer.
It must work with Python 3.9+ (SDK ships 3.9–3.12).
"""

import json
import os
import re
import sys
import traceback


# ---------------------------------------------------------------------------
# Regex patterns for extracting assignments from Python blocks and
# music/audio from UserStatement lines (same logic as regex parser).
# ---------------------------------------------------------------------------

RE_ASSIGN = re.compile(
    r"^\s*(\w+)\s*(?:=|\+=|-=|\*=|/=|//=|%=|\*\*=|&=|\|=|\^=|<<=|>>=)\s*(.*)"
)
RE_AUGMENTED = re.compile(
    r"^\s*(\w+)\s*(\+=|-=|\*=|/=|//=|%=|\*\*=|&=|\|=|\^=|<<=|>>=)\s*(.*)"
)
RE_PLAY = re.compile(
    r'^\s*play\s+(music|sound|voice|audio)\s+"([^"]+)"', re.IGNORECASE
)
RE_QUEUE = re.compile(
    r'^\s*queue\s+(music|sound)\s+"([^"]+)"', re.IGNORECASE
)
RE_VOICE = re.compile(r'^\s*voice\s+"([^"]+)"', re.IGNORECASE)
RE_STOP = re.compile(r"^\s*stop\s+(music|sound|voice|audio)", re.IGNORECASE)

RE_CHARACTER = re.compile(
    r"""Character\(\s*["']([^"']+)["']""", re.IGNORECASE
)


def init_sdk(sdk_path, game_dir):
    """Minimal SDK init — parser only, no SDL/display."""
    sys.path.insert(0, sdk_path)

    # Must set environment before importing renpy
    os.environ.setdefault("RENPY_NO_DISPLAY", "1")

    import renpy  # noqa: E402

    renpy.config.basedir = game_dir
    renpy.config.gamedir = game_dir
    renpy.config.renpy_base = sdk_path

    # Mock the script object that PyCode.__init__ expects
    class FakeScript:
        record_pycode = False
        all_pycode = []
        all_pyexpr = []

    renpy.game.script = FakeScript()

    # Import parser after config is set
    import renpy.parser  # noqa: E402

    return renpy


def get_version(renpy):
    """Get Ren'Py version string."""
    try:
        return getattr(renpy, "version_only", None) or str(
            getattr(renpy, "version_tuple", "unknown")
        )
    except Exception:
        return "unknown"


def flatten_ast(node):
    """Recursively collect all AST nodes from a tree."""
    nodes = [node]
    children = getattr(node, "get_children", None)
    if children is not None:
        for child in children():
            nodes.extend(flatten_ast(child))
    return nodes


def extract_from_node(node, renpy):
    """Extract data from a single AST node into categorized lists.

    Returns a dict with keys matching our protocol:
    labels, jumps, calls, dynamic_jumps, variables, menus, scenes,
    shows, images, music, characters, dialogue, conditions.
    """
    result = {
        "labels": [],
        "jumps": [],
        "calls": [],
        "dynamic_jumps": [],
        "variables": [],
        "menus": [],
        "scenes": [],
        "shows": [],
        "images": [],
        "music": [],
        "characters": [],
        "dialogue": [],
        "conditions": [],
    }

    line = getattr(node, "linenumber", 0)
    cls_name = type(node).__name__

    if cls_name == "Label":
        name = getattr(node, "name", None)
        if name:
            result["labels"].append({"name": name, "line": line})

    elif cls_name == "Jump":
        target = getattr(node, "target", None)
        is_expr = getattr(node, "expression", False)
        if is_expr:
            result["dynamic_jumps"].append(
                {"expression": str(target or ""), "line": line}
            )
        elif target:
            result["jumps"].append({"target": target, "line": line})

    elif cls_name == "Call":
        target = getattr(node, "label", None)
        is_expr = getattr(node, "expression", False)
        if is_expr:
            result["dynamic_jumps"].append(
                {"expression": str(target or ""), "line": line}
            )
        elif target:
            result["calls"].append({"target": target, "line": line})

    elif cls_name == "Return":
        pass  # Used in menu analysis only

    elif cls_name == "Say":
        who = getattr(node, "who", None)
        if who:
            result["dialogue"].append({"speaker": who, "line": line})

    elif cls_name == "Scene":
        imspec = getattr(node, "imspec", None)
        if imspec and imspec[0]:
            image_name = " ".join(imspec[0])
            transition = None
            # imspec format varies; transition info may be at index 3
            if len(imspec) > 3 and imspec[3]:
                transition = str(imspec[3])
            result["scenes"].append(
                {"image_name": image_name, "line": line, "transition": transition}
            )

    elif cls_name == "Show":
        imspec = getattr(node, "imspec", None)
        if imspec and imspec[0]:
            image_name = " ".join(imspec[0])
            result["shows"].append({"image_name": image_name, "line": line})

    elif cls_name == "Image":
        imgname = getattr(node, "imgname", None)
        code = getattr(node, "code", None)
        if imgname:
            name = " ".join(imgname) if isinstance(imgname, (list, tuple)) else str(imgname)
            value = getattr(code, "source", None) if code else None
            result["images"].append({"name": name, "line": line, "value": value})

    elif cls_name in ("Define", "Default"):
        varname = getattr(node, "varname", None)
        store = getattr(node, "store", "store")
        code = getattr(node, "code", None)
        source = getattr(code, "source", "") if code else ""

        if varname:
            kind = "define" if cls_name == "Define" else "default"
            # Build full variable name with store prefix
            if store and store != "store":
                full_name = store + "." + varname
            else:
                full_name = varname

            result["variables"].append(
                {"name": full_name, "line": line, "kind": kind, "value": source}
            )

            # Check if it's a Character definition
            char_match = RE_CHARACTER.search(source)
            if char_match:
                result["characters"].append(
                    {
                        "shorthand": varname,
                        "display_name": char_match.group(1),
                        "line": line,
                    }
                )

    elif cls_name == "Python":
        code = getattr(node, "code", None)
        source = getattr(code, "source", "") if code else ""
        if source:
            for src_line in source.splitlines():
                aug_m = RE_AUGMENTED.match(src_line)
                if aug_m:
                    result["variables"].append(
                        {
                            "name": aug_m.group(1),
                            "line": line,
                            "kind": "augment",
                            "value": aug_m.group(3).strip(),
                        }
                    )
                else:
                    m = RE_ASSIGN.match(src_line)
                    if m:
                        result["variables"].append(
                            {
                                "name": m.group(1),
                                "line": line,
                                "kind": "assign",
                                "value": m.group(2).strip(),
                            }
                        )

    elif cls_name == "UserStatement":
        stmt_line = getattr(node, "line", "")
        _extract_music(stmt_line, line, result)

    elif cls_name == "Menu":
        items = getattr(node, "items", [])
        choices = []
        for item in items:
            # Menu items: (label, condition, block)
            if len(item) >= 3 and item[2] is not None:
                text = item[0] or ""
                condition = item[1]
                block = item[2]
                content_lines = len(block) if block else 0
                has_jump = False
                has_return = False
                if block:
                    for child in block:
                        child_name = type(child).__name__
                        if child_name == "Jump":
                            has_jump = True
                        elif child_name == "Return":
                            has_return = True
                choices.append(
                    {
                        "text": text,
                        "line": getattr(item[2][0], "linenumber", line)
                        if item[2]
                        else line,
                        "content_lines": content_lines,
                        "has_jump": has_jump,
                        "has_return": has_return,
                        "condition": condition,
                    }
                )
        if choices:
            result["menus"].append({"line": line, "choices": choices})

    elif cls_name == "If":
        entries = getattr(node, "entries", [])
        for entry in entries:
            # entry = (condition_expr, block)
            if len(entry) >= 1 and entry[0]:
                cond = str(entry[0])
                result["conditions"].append({"expression": cond, "line": line})

    # Skip Screen, Transform, etc. — not in current model

    return result


def _extract_music(stmt_line, line_num, result):
    """Extract music/audio references from a UserStatement line."""
    m = RE_PLAY.match(stmt_line)
    if m:
        kind = m.group(1).lower()
        action = kind if kind != "music" else "play"
        result["music"].append(
            {"path": m.group(2), "line": line_num, "action": action}
        )
        return

    m = RE_QUEUE.match(stmt_line)
    if m:
        result["music"].append(
            {"path": m.group(2), "line": line_num, "action": "queue"}
        )
        return

    m = RE_VOICE.match(stmt_line)
    if m:
        result["music"].append(
            {"path": m.group(1), "line": line_num, "action": "voice"}
        )
        return

    m = RE_STOP.match(stmt_line)
    if m:
        result["music"].append(
            {"path": "", "line": line_num, "action": "stop"}
        )


def merge_results(target, source):
    """Merge source result dict into target result dict."""
    for key in target:
        if key in source:
            target[key].extend(source[key])


def parse_file_with_sdk(renpy, filepath, game_dir):
    """Parse a single .rpy file using the SDK parser."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            filedata = f.read()
    except (OSError, IOError) as exc:
        return None, str(exc)

    try:
        ast_nodes = renpy.parser.parse(filepath, filedata)
    except Exception as exc:
        return None, str(exc)

    if ast_nodes is None:
        return None, "Parser returned None"

    file_result = {
        "labels": [],
        "jumps": [],
        "calls": [],
        "dynamic_jumps": [],
        "variables": [],
        "menus": [],
        "scenes": [],
        "shows": [],
        "images": [],
        "music": [],
        "characters": [],
        "dialogue": [],
        "conditions": [],
    }

    for top_node in ast_nodes:
        for node in flatten_ast(top_node):
            node_data = extract_from_node(node, renpy)
            merge_results(file_result, node_data)

    return file_result, None


def main():
    """Entry point: read JSON from stdin, parse files, write JSON to stdout."""
    try:
        request = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump(
            {"success": False, "errors": [{"file": "", "message": str(exc)}]},
            sys.stdout,
        )
        return

    sdk_path = request.get("sdk_path", "")
    game_dir = request.get("game_dir", "")
    files = request.get("files", [])

    # Initialize SDK
    try:
        renpy = init_sdk(sdk_path, game_dir)
    except Exception as exc:
        json.dump(
            {
                "success": False,
                "errors": [
                    {"file": "", "message": "SDK init failed: " + str(exc)}
                ],
            },
            sys.stdout,
        )
        traceback.print_exc(file=sys.stderr)
        return

    version = get_version(renpy)
    results = {}
    errors = []

    for filepath in files:
        file_result, error = parse_file_with_sdk(renpy, filepath, game_dir)
        if error:
            errors.append({"file": filepath, "message": error})
            print(
                "WARNING: Failed to parse {}: {}".format(filepath, error),
                file=sys.stderr,
            )
        else:
            results[filepath] = file_result

    response = {
        "success": True,
        "version": version,
        "results": results,
        "errors": errors,
    }

    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
