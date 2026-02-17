"""Tests for the Ren'Py parser."""

import textwrap
from pathlib import Path

from renpy_analyzer.parser import parse_file


def _write_rpy(tmp_path: Path, content: str) -> str:
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


def test_parse_labels(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            "Hello"
        label chapter2:
            "World"
    """)
    result = parse_file(path)
    names = [lbl.name for lbl in result["labels"]]
    assert names == ["start", "chapter2"]


def test_parse_jumps(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            jump chapter2
            jump ending
    """)
    result = parse_file(path)
    targets = [j.target for j in result["jumps"]]
    assert targets == ["chapter2", "ending"]


def test_parse_calls(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            call helper
            call chapter2 from _start_1
    """)
    result = parse_file(path)
    targets = [c.target for c in result["calls"]]
    assert targets == ["helper", "chapter2"]


def test_parse_defaults(tmp_path):
    path = _write_rpy(tmp_path, """\
        default Lydia = 0
        default PlayFight = False
        default marysex4_Slow_3 = False
    """)
    result = parse_file(path)
    vars_ = [(v.name, v.kind) for v in result["variables"]]
    assert vars_ == [
        ("Lydia", "default"),
        ("PlayFight", "default"),
        ("marysex4_Slow_3", "default"),
    ]


def test_parse_assignments(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            $ Lydia += 1
            $ ShellySex3 = True
            $ Temp1 = 0
    """)
    result = parse_file(path)
    vars_ = [(v.name, v.kind) for v in result["variables"]]
    assert ("Lydia", "augment") in vars_
    assert ("ShellySex3", "assign") in vars_
    assert ("Temp1", "assign") in vars_


def test_skip_python_calls(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            $ renpy.pause()
            $ renpy.movie_cutscene("movie.webm")
    """)
    result = parse_file(path)
    assert len(result["variables"]) == 0


def test_parse_characters(tmp_path):
    path = _write_rpy(tmp_path, """\
        define mc = Character("[name]", color="#c5d0b7")
        define l = Character("Lydia", color="#d0b7c5")
    """)
    result = parse_file(path)
    chars = [(c.shorthand, c.display_name) for c in result["characters"]]
    assert chars == [("mc", "[name]"), ("l", "Lydia")]


def test_parse_scenes(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            scene ch12_morning13_1 with dissolve
            scene black with fade
            scene meanwhile with dissolve
    """)
    result = parse_file(path)
    scenes = [(s.image_name, s.transition) for s in result["scenes"]]
    assert scenes == [
        ("ch12_morning13_1", "dissolve"),
        ("black", "fade"),
        ("meanwhile", "dissolve"),
    ]


def test_parse_images(tmp_path):
    path = _write_rpy(tmp_path, """\
        image bedroom1_slow_1 = Movie(play="images/animations/ch1/bedroom1_slow_1.webm")
        image bg barbpan1_1:
            "barbpan1_1"
    """)
    result = parse_file(path)
    names = [i.name for i in result["images"]]
    assert "bedroom1_slow_1" in names
    assert "bg barbpan1_1" in names


def test_parse_music(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            play music "/music/in_my_heaven.mp3"
            stop music
    """)
    result = parse_file(path)
    assert len(result["music"]) == 2
    assert result["music"][0].path == "/music/in_my_heaven.mp3"
    assert result["music"][1].action == "stop"


def test_parse_menu(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            menu:
                "Choice A":
                    mc "Picked A"
                    jump ending
                "Choice B" if flag == False:
                    mc "Picked B"
                    mc "More text"
                    mc "Even more"
        label ending:
            return
    """)
    result = parse_file(path)
    assert len(result["menus"]) == 1
    menu = result["menus"][0]
    assert len(menu.choices) == 2
    assert menu.choices[0].text == "Choice A"
    assert menu.choices[0].has_jump is True
    assert menu.choices[0].condition is None
    assert menu.choices[1].text == "Choice B"
    assert menu.choices[1].condition == "flag == False"
    assert menu.choices[1].content_lines == 3


def test_parse_conditions(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            if SamSex2 or SamSex3 == True:
                jump a
            elif LydiaMary3Some1 == True or MarySolo == True:
                jump b
    """)
    result = parse_file(path)
    exprs = [c.expression for c in result["conditions"]]
    assert "SamSex2 or SamSex3 == True" in exprs
    assert "LydiaMary3Some1 == True or MarySolo == True" in exprs


def test_parse_dialogue(tmp_path):
    path = _write_rpy(tmp_path, """\
        label start:
            mc "Hello world"
            l "Hi there"
            scene black with fade
    """)
    result = parse_file(path)
    speakers = [d.speaker for d in result["dialogue"]]
    assert speakers == ["mc", "l"]
    assert "scene" not in speakers


def test_sound_voice_audio_parsing(tmp_path):
    """Parser should capture play sound, play voice, queue music, voice statement."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(textwrap.dedent("""\
        label start:
            play sound "sfx/click.ogg"
            play voice "voice/ch1_001.ogg"
            queue music "bgm/theme2.ogg"
            voice "voice/line001.ogg"
            play audio "ambient/rain.ogg"
    """), encoding="utf-8")
    result = parse_file(str(rpy))
    assert len(result["music"]) == 5
    actions = {m.action for m in result["music"]}
    assert "sound" in actions
    assert "voice" in actions
    assert "queue" in actions
    assert "audio" in actions
    paths = {m.path for m in result["music"]}
    assert "sfx/click.ogg" in paths
    assert "voice/ch1_001.ogg" in paths
    assert "bgm/theme2.ogg" in paths
    assert "voice/line001.ogg" in paths
    assert "ambient/rain.ogg" in paths


def test_dotted_default_not_split(tmp_path):
    path = _write_rpy(tmp_path, """\
        default persistent.s2 = s2
    """)
    result = parse_file(path)
    assert result["variables"][0].name == "persistent.s2"


def test_multiword_scene_show(tmp_path):
    """scene bg park sunset should capture full image name and tag."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(textwrap.dedent("""\
        label start:
            scene bg park sunset with dissolve
            show eileen happy at right
    """), encoding="utf-8")
    result = parse_file(str(rpy))
    assert len(result["scenes"]) == 1
    assert result["scenes"][0].image_name == "bg park sunset"
    assert result["scenes"][0].transition == "dissolve"
    assert len(result["shows"]) == 1
    assert result["shows"][0].image_name == "eileen happy"
