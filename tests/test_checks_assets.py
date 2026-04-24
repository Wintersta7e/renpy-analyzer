"""Tests for assets check."""

import textwrap

from renpy_analyzer.checks.assets import check
from renpy_analyzer.project import load_project


def _project_with_images(tmp_path, script, images=None):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(textwrap.dedent(script), encoding="utf-8")
    if images:
        for path_str in images:
            p = game / path_str
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"fake")
    return load_project(str(tmp_path))


def test_undefined_scene(tmp_path):
    model = _project_with_images(
        tmp_path,
        """\
        image ch1_bg = "bg.png"
        label start:
            scene ch1_bg with dissolve
            scene meanwhile with dissolve
    """,
    )
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 1
    assert "meanwhile" in undef[0].title


def test_missing_audio_file_detected(tmp_path):
    """Audio file reference with missing file should be flagged."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play sound "sfx/nonexistent.ogg"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    audio = [f for f in findings if "audio" in f.title.lower() or "Missing" in f.title]
    assert len(audio) >= 1


def test_builtin_scene_not_flagged(tmp_path):
    model = _project_with_images(
        tmp_path,
        """\
        label start:
            scene black with fade
    """,
    )
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 0


def test_empty_model_returns_empty(tmp_path):
    """Assets check on empty model should return no findings."""
    from renpy_analyzer.models import ProjectModel

    model = ProjectModel(root_dir=str(tmp_path))
    findings = check(model)
    assert findings == []


def test_images_subdir_auto_detection(tmp_path):
    """Files in game/images/ subdirectories register by lowercased stem only.

    Ren'Py's _scan_images_directory uses only os.path.basename, so
    images/Chapter 1/Foo/ch1_bar_1.webp -> image name 'ch1_bar_1'.
    """
    game = tmp_path / "game"
    game.mkdir()
    # Create image file in nested images/ subdirectory (real-world layout)
    subdir = game / "images" / "Chapter 1" / "Scene1"
    subdir.mkdir(parents=True)
    (subdir / "ch1_scene1_1.webp").write_bytes(b"fake webp")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            scene ch1_scene1_1 with dissolve
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 0


def test_audio_file_exists_no_finding(tmp_path):
    """Audio reference to an existing file should produce no finding."""
    game = tmp_path / "game"
    game.mkdir()
    sfx = game / "sfx"
    sfx.mkdir()
    (sfx / "click.ogg").write_bytes(b"fake audio")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play sound "sfx/click.ogg"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    audio = [f for f in findings if "audio" in f.title.lower() or "Missing" in f.title]
    assert len(audio) == 0


def test_audio_from_prefix_stripped(tmp_path):
    """`<from N>` modifier must be stripped before filesystem lookup."""
    game = tmp_path / "game"
    game.mkdir()
    music = game / "audio" / "music"
    music.mkdir(parents=True)
    (music / "TheOne.opus").write_bytes(b"fake audio")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play music "<from 8>audio/music/TheOne.opus"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if f.title.startswith("Missing audio")]
    assert missing == [], f"Expected no missing-audio finding; got {[f.description for f in missing]}"


def test_audio_combined_prefix_stripped(tmp_path):
    """Combined `<from N to M>` modifier must be stripped before filesystem lookup."""
    game = tmp_path / "game"
    game.mkdir()
    music = game / "audio"
    music.mkdir()
    (music / "bgm.ogg").write_bytes(b"fake audio")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play music "<from 5.0 to 10.0>audio/bgm.ogg"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if f.title.startswith("Missing audio")]
    assert missing == []


def test_audio_silence_only_no_finding(tmp_path):
    """A `<silence N>` pseudo-path has no filename and must not trigger a missing-file check."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play sound "<silence 3.0>"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if f.title.startswith("Missing audio")]
    assert missing == []


def test_audio_prefix_stripped_still_flags_missing_file(tmp_path):
    """After stripping `<from N>`, a genuinely missing file is still flagged."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play music "<from 8>audio/music/ghost.opus"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if f.title.startswith("Missing audio")]
    assert len(missing) == 1
    # The reported path should be the stripped version, not include the prefix.
    assert "<from" not in missing[0].description
    assert "audio/music/ghost.opus" in missing[0].description


def test_scene_white_not_builtin(tmp_path):
    """'scene white' should be flagged — white is NOT a Ren'Py builtin image."""
    model = _project_with_images(
        tmp_path,
        """\
        label start:
            scene white with fade
    """,
    )
    findings = check(model)
    undef = [f for f in findings if "Undefined" in f.title]
    assert len(undef) == 1
    assert "white" in undef[0].title


def test_audio_case_mismatch(tmp_path):
    """Audio reference with wrong case should produce a case mismatch finding."""
    game = tmp_path / "game"
    game.mkdir()
    sfx = game / "sfx"
    sfx.mkdir()
    (sfx / "Click.ogg").write_bytes(b"fake audio")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            play sound "sfx/click.ogg"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    case = [f for f in findings if "case mismatch" in f.title.lower()]
    assert len(case) == 1


# --- Reserved keyword tests ---


def test_reserved_keyword_in_image_def(tmp_path):
    """Image definition with reserved keyword in tag should be flagged."""
    model = _project_with_images(
        tmp_path,
        """\
        image cg s05 sh behind = "cg/s05_sh_behind.png"
        label start:
            pass
    """,
    )
    findings = check(model)
    kw = [f for f in findings if "reserved" in f.title.lower()]
    assert len(kw) == 1
    assert "behind" in kw[0].title
    assert kw[0].severity.name == "HIGH"


def test_reserved_keyword_in_scene(tmp_path):
    """Scene with reserved keyword consumed by regex produces no keyword finding."""
    model = _project_with_images(
        tmp_path,
        """\
        image bg room = "bg/room.png"
        label start:
            scene bg room with dissolve
    """,
    )
    findings = check(model)
    kw = [f for f in findings if "reserved" in f.title.lower()]
    # 'with' is consumed by RE_SCENE as transition, not part of image_name
    assert len(kw) == 0


def test_reserved_keyword_in_show(tmp_path):
    """Show statement with reserved keyword in image name should be flagged."""
    model = _project_with_images(
        tmp_path,
        """\
        image npc expression happy = "npc/happy.png"
        label start:
            show npc expression happy
    """,
    )
    findings = check(model)
    kw = [f for f in findings if "reserved" in f.title.lower()]
    # RE_SHOW skips 'expression' via negative lookahead — but image def is checked
    assert len(kw) >= 1


def test_no_reserved_keyword_clean_names(tmp_path):
    """Normal image names without reserved keywords produce no findings."""
    model = _project_with_images(
        tmp_path,
        """\
        image bg classroom = "bg/classroom.png"
        image cg ending01 = "cg/ending01.png"
        label start:
            scene bg classroom
    """,
    )
    findings = check(model)
    kw = [f for f in findings if "reserved" in f.title.lower()]
    assert len(kw) == 0


def test_reserved_keyword_multiple_in_tag(tmp_path):
    """Multiple reserved keywords in one tag should all be reported."""
    model = _project_with_images(
        tmp_path,
        """\
        image cg scene behind = "cg/bad.png"
        label start:
            pass
    """,
    )
    findings = check(model)
    kw = [f for f in findings if "reserved" in f.title.lower()]
    assert len(kw) == 1
    # Both 'scene' and 'behind' mentioned in description
    assert "scene" in kw[0].description.lower()
    assert "behind" in kw[0].description.lower()


# --- Scene expression path tests ---


def test_scene_expression_missing_file(tmp_path):
    """scene expression with nonexistent file path should be flagged."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            scene expression "images/maps/Nonexistent.png"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if "scene expression" in f.title.lower()]
    assert len(missing) == 1
    assert missing[0].severity.name == "HIGH"


def test_scene_expression_existing_file(tmp_path):
    """scene expression with existing file path should not be flagged."""
    game = tmp_path / "game"
    game.mkdir()
    img_dir = game / "images" / "maps"
    img_dir.mkdir(parents=True)
    (img_dir / "Classroom.png").write_bytes(b"fake png")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            scene expression "images/maps/Classroom.png"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if "scene expression" in f.title.lower()]
    assert len(missing) == 0


def test_scene_expression_variable_not_checked(tmp_path):
    """scene expression with a variable (not string) should be ignored."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            scene expression my_image_var
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if "scene expression" in f.title.lower()]
    assert len(missing) == 0


def test_scene_expression_rpa_skipped(tmp_path):
    """scene expression path check should be skipped when .rpa archives present."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "archive.rpa").write_bytes(b"fake rpa")
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            scene expression "images/maps/Nonexistent.png"
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if "scene expression" in f.title.lower()]
    assert len(missing) == 0


def test_scene_expression_single_quotes(tmp_path):
    """scene expression with single-quoted path should also be checked."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        textwrap.dedent("""\
        label start:
            scene expression 'images/maps/Missing.png'
    """),
        encoding="utf-8",
    )
    model = load_project(str(tmp_path))
    findings = check(model)
    missing = [f for f in findings if "scene expression" in f.title.lower()]
    assert len(missing) == 1
