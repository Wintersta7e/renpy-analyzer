"""Tests for version detection (version.py)."""

from __future__ import annotations

from renpy_analyzer.version import (
    detect_renpy_version,
    format_version,
    select_sdk,
)


# ---------------------------------------------------------------------------
# detect_renpy_version — 8.x format (vc_version.py with version string)
# ---------------------------------------------------------------------------


def test_detect_version_8x_sdk(tmp_path):
    """Detect version from vc_version.py (8.x+ format)."""
    renpy_dir = tmp_path / "renpy"
    renpy_dir.mkdir()
    (renpy_dir / "vc_version.py").write_text(
        "branch = 'fix'\nnightly = False\nofficial = True\nversion = '8.5.2.26010301'\nversion_name = 'In Good Health'\n"
    )
    ver = detect_renpy_version(str(tmp_path))
    assert ver == (8, 5, 2)


def test_detect_version_7x_sdk_unicode_prefix(tmp_path):
    """Detect version from vc_version.py with u'' string prefix (7.x SDKs)."""
    renpy_dir = tmp_path / "renpy"
    renpy_dir.mkdir()
    (renpy_dir / "vc_version.py").write_text(
        "branch = u'fix'\nnightly = False\nofficial = True\nversion = u'7.8.7.25031702'\nversion_name = u'Straight on Till Morning'\n"
    )
    ver = detect_renpy_version(str(tmp_path))
    assert ver == (7, 8, 7)


def test_detect_version_8x_game_with_game_subdir(tmp_path):
    """Detect version from game/renpy/vc_version.py."""
    renpy_dir = tmp_path / "game" / "renpy"
    renpy_dir.mkdir(parents=True)
    (renpy_dir / "vc_version.py").write_text(
        "version = '8.1.3.23091805'\n"
    )
    ver = detect_renpy_version(str(tmp_path))
    assert ver == (8, 1, 3)


# ---------------------------------------------------------------------------
# detect_renpy_version — 7.x format (version_tuple in __init__.py)
# ---------------------------------------------------------------------------


def test_detect_version_7x_init(tmp_path):
    """Detect version from __init__.py version_tuple (7.x format)."""
    renpy_dir = tmp_path / "renpy"
    renpy_dir.mkdir()
    (renpy_dir / "__init__.py").write_text(
        "if PY2:\n    version_tuple = (7, 4, 10, vc_version)\nelse:\n    version_tuple = (8, 0, 0, vc_version)\n"
    )
    ver = detect_renpy_version(str(tmp_path))
    assert ver == (7, 4, 10)


def test_detect_version_prefers_vc_version_over_init(tmp_path):
    """vc_version.py is checked first and takes priority over __init__.py."""
    renpy_dir = tmp_path / "renpy"
    renpy_dir.mkdir()
    (renpy_dir / "vc_version.py").write_text("version = '8.2.0.12345'\n")
    (renpy_dir / "__init__.py").write_text("version_tuple = (7, 0, 0, 0)\n")
    ver = detect_renpy_version(str(tmp_path))
    assert ver == (8, 2, 0)


def test_detect_version_old_vc_version_no_string(tmp_path):
    """Old vc_version.py with only integer vc_version falls back to __init__.py."""
    renpy_dir = tmp_path / "renpy"
    renpy_dir.mkdir()
    (renpy_dir / "vc_version.py").write_text(
        "vc_version = 2178\nofficial = True\nnightly = False\n"
    )
    (renpy_dir / "__init__.py").write_text(
        "version_tuple = (7, 4, 10, vc_version)\n"
    )
    ver = detect_renpy_version(str(tmp_path))
    assert ver == (7, 4, 10)


def test_detect_version_no_renpy_dir(tmp_path):
    """Returns None when no renpy/ directory exists."""
    ver = detect_renpy_version(str(tmp_path))
    assert ver is None


def test_detect_version_empty_renpy_dir(tmp_path):
    """Returns None when renpy/ exists but has no version files."""
    (tmp_path / "renpy").mkdir()
    ver = detect_renpy_version(str(tmp_path))
    assert ver is None


# ---------------------------------------------------------------------------
# format_version
# ---------------------------------------------------------------------------


def test_format_version_3_parts():
    assert format_version((8, 5, 2)) == "8.5.2"


def test_format_version_4_parts():
    assert format_version((7, 4, 10, 2178)) == "7.4.10.2178"


def test_format_version_1_part():
    assert format_version((9,)) == "9"


# ---------------------------------------------------------------------------
# select_sdk
# ---------------------------------------------------------------------------


def test_select_sdk_major_match(tmp_path):
    """Selects SDK with matching major version."""
    sdk7 = tmp_path / "sdk7"
    sdk8 = tmp_path / "sdk8"
    for d in (sdk7, sdk8):
        (d / "renpy").mkdir(parents=True)
    (sdk7 / "renpy" / "vc_version.py").write_text("version = '7.5.3.1234'\n")
    (sdk8 / "renpy" / "vc_version.py").write_text("version = '8.5.2.5678'\n")

    # Game is 7.x → should pick SDK 7
    result = select_sdk((7, 3, 0), [str(sdk7), str(sdk8)])
    assert result == str(sdk7)

    # Game is 8.x → should pick SDK 8
    result = select_sdk((8, 1, 0), [str(sdk7), str(sdk8)])
    assert result == str(sdk8)


def test_select_sdk_no_match(tmp_path):
    """Returns None when no SDK matches the game's major version."""
    sdk8 = tmp_path / "sdk8"
    (sdk8 / "renpy").mkdir(parents=True)
    (sdk8 / "renpy" / "vc_version.py").write_text("version = '8.5.2.5678'\n")

    result = select_sdk((7, 4, 0), [str(sdk8)])
    assert result is None


def test_select_sdk_picks_highest_within_major(tmp_path):
    """When multiple SDKs share a major version, picks the highest."""
    sdk_a = tmp_path / "sdk_old"
    sdk_b = tmp_path / "sdk_new"
    for d in (sdk_a, sdk_b):
        (d / "renpy").mkdir(parents=True)
    (sdk_a / "renpy" / "vc_version.py").write_text("version = '8.1.0.1234'\n")
    (sdk_b / "renpy" / "vc_version.py").write_text("version = '8.5.2.5678'\n")

    result = select_sdk((8, 3, 0), [str(sdk_a), str(sdk_b)])
    assert result == str(sdk_b)


def test_select_sdk_none_game_version():
    """Returns None when game version is None."""
    assert select_sdk(None, ["/some/sdk"]) is None


def test_select_sdk_empty_sdk_list():
    """Returns None when no SDKs are provided."""
    assert select_sdk((8, 0, 0), []) is None
