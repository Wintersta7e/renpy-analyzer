#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bridge worker: runs under the Ren'Py SDK's bundled Python.

Reads a JSON request from stdin, uses the SDK's renpy.parser to parse
.rpy files, walks the AST, and writes a JSON response to stdout.

This file is STANDALONE -- it must not import anything from renpy_analyzer.
It must work with Python 2.7+ (SDK 7.x) and Python 3.9+ (SDK 8.x).
"""

from __future__ import print_function

import collections
import io
import json
import os
import re
import sys
import traceback

# ---------------------------------------------------------------------------
# Regex patterns for extracting assignments from Python blocks and
# music/audio from UserStatement lines (same logic as regex parser).
# ---------------------------------------------------------------------------

RE_ASSIGN = re.compile(r"^\s*(\w+)\s*(?:=|\+=|-=|\*=|/=|//=|%=|\*\*=|&=|\|=|\^=|<<=|>>=)\s*(.*)")
RE_AUGMENTED = re.compile(r"^\s*(\w+)\s*(\+=|-=|\*=|/=|//=|%=|\*\*=|&=|\|=|\^=|<<=|>>=)\s*(.*)")
RE_PLAY = re.compile(r'^\s*play\s+(music|sound|voice|audio)\s+"([^"]+)"', re.IGNORECASE)
RE_QUEUE = re.compile(r'^\s*queue\s+(music|sound)\s+"([^"]+)"', re.IGNORECASE)
RE_VOICE = re.compile(r'^\s*voice\s+"([^"]+)"', re.IGNORECASE)
RE_STOP = re.compile(r"^\s*stop\s+(music|sound|voice|audio)", re.IGNORECASE)

RE_CHARACTER = re.compile(r"""Character\(\s*(?:_\(\s*)?["']([^"']+)["']""", re.IGNORECASE)


def init_sdk(sdk_path, game_dir):
    """Minimal SDK init — parser only, no SDL/display."""
    sys.path.insert(0, sdk_path)

    # Must set environment before importing renpy
    os.environ.setdefault("RENPY_NO_DISPLAY", "1")

    import renpy

    # renpy submodules (config, game, parser, etc.) are NOT loaded by
    # a bare "import renpy".  The SDK's import_all() loads them all.
    renpy.import_all()

    renpy.config.basedir = game_dir
    renpy.config.gamedir = game_dir
    renpy.config.renpy_base = sdk_path

    # Mock the script object that PyCode.__init__ expects
    class FakeScript:
        record_pycode = False
        all_pycode = []  # noqa: RUF012
        all_pyexpr = []  # noqa: RUF012

    renpy.game.script = FakeScript()

    return renpy


def get_version(renpy):
    """Get Ren'Py version string."""
    try:
        return getattr(renpy, "version_only", None) or str(getattr(renpy, "version_tuple", "unknown"))
    except Exception:
        return "unknown"


def flatten_ast(node):
    """Iteratively collect all AST nodes from a tree via BFS.

    Handles both API styles of get_children():
    - Visitor pattern: get_children(callback) calls callback(child)
    - List return: get_children() returns a list of children

    Returns a list of (node, in_init) tuples, where in_init is True
    when the node is inside an Init block.
    """
    result = []
    seen = set()
    # Queue entries: (node, in_init_context)
    queue = collections.deque([(node, False)])
    while queue:
        current, in_init = queue.popleft()
        node_id = id(current)
        if node_id in seen:
            continue
        seen.add(node_id)
        cls_name = type(current).__name__
        # Init nodes and Define/Default are always init-time
        if cls_name == "Init" or cls_name in ("Define", "Default"):
            in_init = True
        result.append((current, in_init))
        get_children = getattr(current, "get_children", None)
        if get_children is None:
            continue
        # Try no-arg call first (returns list), fall back to visitor pattern
        try:
            children = get_children()
            if children:
                for child in children:
                    queue.append((child, in_init))
        except TypeError:
            collected = []
            get_children(collected.append)
            for child in collected:
                queue.append((child, in_init))
    return result


def extract_from_node(node, renpy, in_init=False):
    """Extract data from a single AST node into categorized lists.

    Returns a dict with keys matching our protocol:
    labels, jumps, calls, dynamic_jumps, variables, menus, scenes,
    shows, images, music, characters, dialogue, conditions.
    """
    # Only populate keys that actually have data to avoid allocating
    # 18 empty lists per node (most nodes produce 1-2 entries).
    result = {}

    line = getattr(node, "linenumber", 0)
    cls_name = type(node).__name__

    if cls_name == "Label":
        name = getattr(node, "name", None)
        if name:
            result.setdefault("labels", []).append({"name": name, "line": line})

    elif cls_name == "Jump":
        target = getattr(node, "target", None)
        is_expr = getattr(node, "expression", False)
        if is_expr:
            result.setdefault("dynamic_jumps", []).append({"expression": str(target or ""), "line": line})
        elif target:
            result.setdefault("jumps", []).append({"target": target, "line": line})

    elif cls_name == "Call":
        target = getattr(node, "label", None)
        is_expr = getattr(node, "expression", False)
        if is_expr:
            result.setdefault("dynamic_jumps", []).append({"expression": str(target or ""), "line": line})
        elif target:
            result.setdefault("calls", []).append({"target": target, "line": line})

    elif cls_name == "Return":
        pass  # Used in menu analysis only

    elif cls_name == "Say":
        who = getattr(node, "who", None)
        if who:
            what = getattr(node, "what", "") or ""
            result.setdefault("dialogue", []).append({"speaker": who, "line": line, "text": what})

    elif cls_name == "Scene":
        imspec = getattr(node, "imspec", None)
        if imspec and imspec[0]:
            image_name = " ".join(imspec[0])
            transition = None
            # imspec format varies; transition info may be at index 3
            if len(imspec) > 3 and imspec[3]:
                transition = str(imspec[3])
            result.setdefault("scenes", []).append({"image_name": image_name, "line": line, "transition": transition})

    elif cls_name == "Show":
        imspec = getattr(node, "imspec", None)
        if imspec and imspec[0]:
            image_name = " ".join(imspec[0])
            result.setdefault("shows", []).append({"image_name": image_name, "line": line})

    elif cls_name == "Image":
        imgname = getattr(node, "imgname", None)
        code = getattr(node, "code", None)
        if imgname:
            name = " ".join(imgname) if isinstance(imgname, (list, tuple)) else str(imgname)
            value = getattr(code, "source", None) if code else None
            result.setdefault("images", []).append({"name": name, "line": line, "value": value})

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

            result.setdefault("variables", []).append({"name": full_name, "line": line, "kind": kind, "value": source, "in_init": in_init})

            # Check if it's a Character definition
            char_match = RE_CHARACTER.search(source)
            if char_match:
                result.setdefault("characters", []).append(
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
                    result.setdefault("variables", []).append(
                        {
                            "name": aug_m.group(1),
                            "line": line,
                            "kind": "augment",
                            "value": aug_m.group(3).strip(),
                            "in_init": in_init,
                        }
                    )
                else:
                    m = RE_ASSIGN.match(src_line)
                    if m:
                        result.setdefault("variables", []).append(
                            {
                                "name": m.group(1),
                                "line": line,
                                "kind": "assign",
                                "value": m.group(2).strip(),
                                "in_init": in_init,
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
                        "line": getattr(item[2][0], "linenumber", line) if item[2] else line,
                        "content_lines": content_lines,
                        "has_jump": has_jump,
                        "has_return": has_return,
                        "condition": condition,
                    }
                )
        if choices:
            result.setdefault("menus", []).append({"line": line, "choices": choices})

    elif cls_name == "If":
        entries = getattr(node, "entries", [])
        for entry in entries:
            # entry = (condition_expr, block)
            if len(entry) >= 1 and entry[0]:
                cond = str(entry[0])
                result.setdefault("conditions", []).append({"expression": cond, "line": line})

    elif cls_name == "Screen":
        name = getattr(node, "name", None)
        if name:
            result.setdefault("screen_defs", []).append({"name": name, "line": line})

    elif cls_name == "ShowScreen":
        name = getattr(node, "screen_name", None) or getattr(node, "name", None)
        if isinstance(name, (list, tuple)):
            name = name[0] if name else None
        if name:
            result.setdefault("screen_refs", []).append({"name": str(name), "line": line, "action": "show"})

    elif cls_name == "CallScreen":
        name = getattr(node, "screen_name", None) or getattr(node, "name", None)
        if isinstance(name, (list, tuple)):
            name = name[0] if name else None
        if name:
            result.setdefault("screen_refs", []).append({"name": str(name), "line": line, "action": "call"})

    elif cls_name == "HideScreen":
        name = getattr(node, "screen_name", None) or getattr(node, "name", None)
        if isinstance(name, (list, tuple)):
            name = name[0] if name else None
        if name:
            result.setdefault("screen_refs", []).append({"name": str(name), "line": line, "action": "hide"})

    elif cls_name == "Transform":
        name = getattr(node, "varname", None)
        if name:
            result.setdefault("transform_defs", []).append({"name": name, "line": line})

    elif cls_name == "Translate":
        language = getattr(node, "language", None)
        identifier = getattr(node, "identifier", None)
        if language and identifier:
            result.setdefault("translations", []).append({"language": language, "string_id": identifier, "line": line})

    # Extract transform refs from Show/Scene 'at' clauses
    if cls_name in ("Show", "Scene"):
        imspec = getattr(node, "imspec", None)
        if imspec and len(imspec) > 2 and imspec[2]:
            # imspec[2] is the at_list (list of transform names)
            for t in imspec[2]:
                if isinstance(t, str):
                    result.setdefault("transform_refs", []).append({"name": t, "line": line})

    return result


def _extract_music(stmt_line, line_num, result):
    """Extract music/audio references from a UserStatement line."""
    m = RE_PLAY.match(stmt_line)
    if m:
        kind = m.group(1).lower()
        action = kind if kind != "music" else "play"
        result.setdefault("music", []).append({"path": m.group(2), "line": line_num, "action": action})
        return

    m = RE_QUEUE.match(stmt_line)
    if m:
        result.setdefault("music", []).append({"path": m.group(2), "line": line_num, "action": "queue"})
        return

    m = RE_VOICE.match(stmt_line)
    if m:
        result.setdefault("music", []).append({"path": m.group(1), "line": line_num, "action": "voice"})
        return

    m = RE_STOP.match(stmt_line)
    if m:
        result.setdefault("music", []).append({"path": "", "line": line_num, "action": "stop"})


def merge_results(target, source):
    """Merge source result dict into target result dict."""
    for key in target:
        if key in source:
            target[key].extend(source[key])


def _drain_parse_errors(renpy):
    """Drain and return the module-level parse_errors list.

    renpy.parser.parse() accumulates errors in a global list.  If this
    list is not cleared between files, a single bad file causes every
    subsequent parse() call to return None.  This function uses the
    SDK's get_parse_errors() (which resets the list) or falls back to
    manual clearing for older SDKs.
    """
    errors = []
    get_fn = getattr(renpy.parser, "get_parse_errors", None)
    if get_fn:
        errors = get_fn() or []
        # Defensive: ensure the underlying list is empty even if get_fn()
        # returned errors without clearing them internally.
        err_list = getattr(renpy.parser, "parse_errors", None)
        if err_list:
            del err_list[:]
    else:
        # Older SDKs: clear manually
        err_list = getattr(renpy.parser, "parse_errors", None)
        if err_list:
            errors = list(err_list)
            del err_list[:]
    return errors


def parse_file_with_sdk(renpy, filepath, game_dir):
    """Parse a single .rpy file using the SDK parser."""
    try:
        with io.open(filepath, encoding="utf-8", errors="replace") as f:
            filedata = f.read()
    except OSError as exc:
        return None, str(exc)

    try:
        ast_nodes = renpy.parser.parse(filepath, filedata)
    except Exception as exc:
        # Drain parse_errors to avoid poisoning subsequent files.
        _drain_parse_errors(renpy)
        return None, str(exc)

    # Always drain the module-level parse_errors list after each parse()
    # call.  parse_errors is a global that accumulates across calls — if
    # it is not cleared, a single file's error causes every subsequent
    # file to return None.
    file_errors = _drain_parse_errors(renpy)

    if ast_nodes is None:
        error_msg = "; ".join(file_errors) if file_errors else "Parser returned None"
        return None, error_msg

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
        "screen_defs": [],
        "screen_refs": [],
        "transform_defs": [],
        "transform_refs": [],
        "translations": [],
    }

    for top_node in ast_nodes:
        for node, node_in_init in flatten_ast(top_node):
            node_data = extract_from_node(node, renpy, in_init=node_in_init)
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
                "errors": [{"file": "", "message": "SDK init failed: " + str(exc)}],
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
                "WARNING: Failed to parse %s: %s" % (filepath, error),
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
