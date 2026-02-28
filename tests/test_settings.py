"""Tests for persistent settings (settings.py)."""

import json

from renpy_analyzer.settings import _SETTINGS_FILE, Settings


def test_settings_round_trip(tmp_path, monkeypatch):
    """Save then load — all fields should be restored exactly."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    s = Settings(
        sdk_paths=["/some/sdk", "/other/sdk"],
        game_path="/my/game",
        window_geometry="1200x900+100+50",
        check_toggles={"Labels": True, "Flow": False},
        severity_filters={"CRITICAL": True, "LOW": False},
        sort_column="file",
        sort_ascending=False,
    )
    s.save()

    loaded = Settings.load()
    assert loaded.sdk_paths == ["/some/sdk", "/other/sdk"]
    assert loaded.game_path == "/my/game"
    assert loaded.window_geometry == "1200x900+100+50"
    assert loaded.check_toggles == {"Labels": True, "Flow": False}
    assert loaded.severity_filters == {"CRITICAL": True, "LOW": False}
    assert loaded.sort_column == "file"
    assert loaded.sort_ascending is False


def test_settings_round_trip_defaults(tmp_path, monkeypatch):
    """Round-trip with default values preserves all defaults."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    Settings().save()
    loaded = Settings.load()
    assert loaded.sdk_paths == []
    assert loaded.game_path == ""
    assert loaded.window_geometry == "1050x780"
    assert loaded.check_toggles == {}
    assert loaded.severity_filters == {}
    assert loaded.sort_column == "severity"
    assert loaded.sort_ascending is True


def test_settings_load_missing_file(tmp_path, monkeypatch):
    """Loading from a nonexistent path returns defaults."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path / "nope")

    s = Settings.load()
    assert s.sdk_paths == []
    assert s.game_path == ""
    assert s.window_geometry == "1050x780"
    assert s.check_toggles == {}
    assert s.severity_filters == {}
    assert s.sort_column == "severity"
    assert s.sort_ascending is True


def test_settings_load_corrupt_file(tmp_path, monkeypatch):
    """Corrupt JSON returns defaults without crashing."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text("NOT VALID JSON {{{{", encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == []
    assert s.window_geometry == "1050x780"


def test_settings_load_truncated_json(tmp_path, monkeypatch):
    """Truncated JSON (e.g. from interrupted write) returns defaults."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text('{"sdk_paths": ["/foo"], "game_', encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == []
    assert s.window_geometry == "1050x780"


def test_settings_ignores_unknown_keys(tmp_path, monkeypatch):
    """Unknown keys in the JSON are silently ignored (forward compat)."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {
        "sdk_paths": ["/saved/sdk"],
        "game_path": "/saved/game",
        "future_field": "should be ignored",
        "another_unknown": 42,
    }
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == ["/saved/sdk"]
    assert s.game_path == "/saved/game"
    assert not hasattr(s, "future_field")
    assert not hasattr(s, "another_unknown")
    # Defaults for other fields
    assert s.window_geometry == "1050x780"
    assert s.sort_column == "severity"


def test_settings_rejects_wrong_types(tmp_path, monkeypatch):
    """Fields with wrong types in JSON are discarded; defaults used instead."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {
        "sdk_paths": "not_a_list",          # should be list
        "game_path": "/valid/path",          # correct
        "check_toggles": "all_on",           # should be dict
        "severity_filters": [1, 2, 3],       # should be dict
        "sort_ascending": "yes",             # should be bool
        "sort_column": True,                 # should be str
        "window_geometry": 1050,             # should be str
    }
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    # Only game_path was valid
    assert s.game_path == "/valid/path"
    # All others should be defaults
    assert s.sdk_paths == []
    assert s.check_toggles == {}
    assert s.severity_filters == {}
    assert s.sort_ascending is True
    assert s.sort_column == "severity"
    assert s.window_geometry == "1050x780"


def test_settings_rejects_int_as_bool(tmp_path, monkeypatch):
    """Integer values are not accepted for bool fields (Python int/bool overlap)."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {"sort_ascending": 1}  # int, not bool
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    assert s.sort_ascending is True  # default, not the loaded 1


def test_settings_save_creates_directory(tmp_path, monkeypatch):
    """Save creates the config directory if it doesn't exist."""
    target = tmp_path / "nested" / "dir"
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: target)

    Settings().save()

    assert (target / _SETTINGS_FILE).exists()
    data = json.loads((target / _SETTINGS_FILE).read_text(encoding="utf-8"))
    assert data["sdk_paths"] == []


def test_settings_load_non_dict_json(tmp_path, monkeypatch):
    """JSON that parses to non-dict (e.g. a list) returns defaults."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text("[1, 2, 3]", encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == []
    assert s.window_geometry == "1050x780"


def test_settings_atomic_write_no_temp_residue(tmp_path, monkeypatch):
    """After save, no temp files remain in the config directory."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    Settings(sdk_paths=["/test"]).save()

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == _SETTINGS_FILE


def test_settings_save_overwrites_existing(tmp_path, monkeypatch):
    """Saving twice overwrites the previous file correctly."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    Settings(sdk_paths=["/first"]).save()
    Settings(sdk_paths=["/second"]).save()

    loaded = Settings.load()
    assert loaded.sdk_paths == ["/second"]


# ---------------------------------------------------------------------------
# Migration: old sdk_path (str) → sdk_paths (list)
# ---------------------------------------------------------------------------


def test_settings_migrate_sdk_path_to_sdk_paths(tmp_path, monkeypatch):
    """Old settings with sdk_path string should migrate to sdk_paths list."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {
        "sdk_path": "/old/sdk/path",
        "game_path": "/my/game",
    }
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == ["/old/sdk/path"]
    assert s.game_path == "/my/game"


def test_settings_migrate_empty_sdk_path(tmp_path, monkeypatch):
    """Empty sdk_path string migrates to empty sdk_paths list."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {"sdk_path": "", "game_path": "/game"}
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == []
    assert s.game_path == "/game"


def test_settings_migrate_both_keys_present(tmp_path, monkeypatch):
    """If both sdk_path and sdk_paths exist, sdk_paths wins, old key dropped."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {
        "sdk_path": "/old",
        "sdk_paths": ["/new1", "/new2"],
    }
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == ["/new1", "/new2"]


def test_settings_sdk_paths_filters_non_strings(tmp_path, monkeypatch):
    """Non-string elements in sdk_paths list are filtered out."""
    monkeypatch.setattr("renpy_analyzer.settings._config_path", lambda: tmp_path)

    data = {"sdk_paths": ["/valid", 42, None, "/also-valid", True]}
    filepath = tmp_path / _SETTINGS_FILE
    filepath.write_text(json.dumps(data), encoding="utf-8")

    s = Settings.load()
    assert s.sdk_paths == ["/valid", "/also-valid"]
