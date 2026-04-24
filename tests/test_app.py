"""Tests for GUI-side SDK trust and validation flows."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


class _DummyVar:
    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value


class _DummyWidget:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def configure(self, **kwargs) -> None:
        self.calls.append(("configure", kwargs))

    def grid(self, **kwargs) -> None:
        self.calls.append(("grid", kwargs))

    def grid_remove(self) -> None:
        self.calls.append(("grid_remove", None))

    def set(self, value) -> None:
        self.calls.append(("set", value))

    def get_children(self) -> list[str]:
        return ["finding-1"]

    def delete(self, item_id: str) -> None:
        self.calls.append(("delete", item_id))


class _DummyThread:
    def __init__(self, *, target, args, daemon) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True


@pytest.fixture
def app_module(monkeypatch):
    fake_ctk = types.ModuleType("customtkinter")
    fake_ctk.CTk = object
    monkeypatch.setitem(sys.modules, "customtkinter", fake_ctk)
    sys.modules.pop("renpy_analyzer.app", None)

    import renpy_analyzer.app as app

    return app


def test_load_sdk_entries_skips_invalid_saved_paths(app_module):
    app = app_module.RenpyAnalyzerApp.__new__(app_module.RenpyAnalyzerApp)
    app._settings = SimpleNamespace(sdk_paths=["/invalid/sdk", "/valid/sdk"])

    def _is_valid(path: str) -> bool:
        return path == "/valid/sdk"

    with (
        pytest.MonkeyPatch.context() as patch_ctx,
    ):
        patch_ctx.setattr(app_module, "validate_sdk_path", _is_valid)
        patch_ctx.setattr(app_module, "detect_sdk_version", lambda _path: "8.5.2")
        app._load_sdk_entries()

    assert app._sdk_entries == [("/valid/sdk", "8.5.2")]


def test_resolve_sdk_for_analysis_revalidates_explicit_selection(app_module):
    app = app_module.RenpyAnalyzerApp.__new__(app_module.RenpyAnalyzerApp)
    app._sdk_entries = [("/sdk/path", "8.5.2")]
    app._sdk_dropdown_var = _DummyVar("8.5.2 — /sdk/path")

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setattr(app_module, "validate_sdk_path", lambda _path: False)
        assert app._resolve_sdk_for_analysis("/game") is None


def test_run_analysis_passes_trust_flag_from_resolved_sdk(app_module):
    scheduled: list[tuple[int, object, tuple[object, ...]]] = []
    app = SimpleNamespace(
        _resolved_sdk_path="/sdk/path",
        _cancel_event=SimpleNamespace(is_set=lambda: False),
        after=lambda delay, callback, *args: scheduled.append((delay, callback, args)),
        _update_progress=lambda _msg, _frac: None,
        _analysis_complete=lambda _findings, _project_path: None,
        _analysis_cancelled=lambda: None,
        _analysis_failed=lambda _message: None,
    )

    with pytest.MonkeyPatch.context() as patch_ctx:
        calls: list[dict[str, object]] = []

        def _run_analysis(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return []

        patch_ctx.setattr(app_module, "run_analysis", _run_analysis)
        app_module.RenpyAnalyzerApp._run_analysis(app, "/game", ["Labels"])

    assert calls[0]["kwargs"]["sdk_path"] == "/sdk/path"
    assert calls[0]["kwargs"]["trust_sdk"] is True
    assert scheduled[0][0] == 100


def test_start_analysis_declined_sdk_falls_back_to_regex(app_module, monkeypatch, tmp_path):
    (tmp_path / "game").mkdir()
    created_threads: list[_DummyThread] = []

    def _make_thread(*, target, args, daemon):
        thread = _DummyThread(target=target, args=args, daemon=daemon)
        created_threads.append(thread)
        return thread

    monkeypatch.setattr(app_module.threading, "Thread", _make_thread)

    app = SimpleNamespace(
        _is_busy=lambda: False,
        _path_var=_DummyVar(str(tmp_path)),
        _status_var=_DummyVar(""),
        _check_vars={"Labels": _DummyVar(True)},
        _resolve_sdk_for_analysis=lambda _path: "/sdk/path",
        _confirm_sdk_trust=lambda _path: False,
        _analyze_btn=_DummyWidget(),
        _export_btn=_DummyWidget(),
        _browse_game_btn=_DummyWidget(),
        _add_sdk_btn=_DummyWidget(),
        _remove_sdk_btn=_DummyWidget(),
        _tree=_DummyWidget(),
        _cancel_event=SimpleNamespace(clear=lambda: None),
        _cancel_btn=_DummyWidget(),
        _progress_bar=_DummyWidget(),
        _progress_label=_DummyWidget(),
        _tree_frame=_DummyWidget(),
        _progress_frame=_DummyWidget(),
        _run_analysis=lambda *_args: None,
        _analysis_thread=None,
    )

    app_module.RenpyAnalyzerApp._start_analysis(app)

    assert app._resolved_sdk_path is None
    assert app._status_var.get() == "SDK parser skipped — using regex parser."
    assert created_threads[0].args == (str(tmp_path), ["Labels"])
    assert created_threads[0].started is True
