"""Tests for logging infrastructure."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

from renpy_analyzer.log import setup_logging
from renpy_analyzer.project import load_project


def _clear_logger() -> None:
    """Remove all handlers from the renpy_analyzer logger so each test starts fresh."""
    logger = logging.getLogger("renpy_analyzer")
    logger.handlers.clear()


def test_setup_logging_creates_stderr_handler():
    _clear_logger()
    setup_logging()
    logger = logging.getLogger("renpy_analyzer")
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert logger.level == logging.WARNING
    _clear_logger()


def test_setup_logging_verbose_sets_debug():
    _clear_logger()
    setup_logging(verbose=True)
    logger = logging.getLogger("renpy_analyzer")
    assert logger.level == logging.DEBUG
    _clear_logger()


def test_setup_logging_with_log_file(tmp_path):
    _clear_logger()
    log_file = str(tmp_path / "test.log")
    setup_logging(log_file=log_file)
    logger = logging.getLogger("renpy_analyzer")
    assert len(logger.handlers) == 2
    assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    # Write a message and verify it reaches the file
    logger.warning("test message")
    for h in logger.handlers:
        h.flush()
    content = Path(log_file).read_text(encoding="utf-8")
    assert "test message" in content
    _clear_logger()


def test_setup_logging_idempotent():
    _clear_logger()
    setup_logging()
    setup_logging()  # second call should be a no-op
    logger = logging.getLogger("renpy_analyzer")
    assert len(logger.handlers) == 1
    _clear_logger()


def test_project_loader_logs_warning_on_bad_file(tmp_path, caplog, monkeypatch):
    _clear_logger()
    game = tmp_path / "game"
    game.mkdir()
    # Write a valid file
    (game / "good.rpy").write_text(textwrap.dedent("""\
        label start:
            "Hello"
    """), encoding="utf-8")
    # Write a second file that we'll force to fail via monkeypatch
    (game / "bad.rpy").write_text("label broken:\n    jump x\n", encoding="utf-8")

    from renpy_analyzer import project as project_mod

    _real_parse = project_mod.parse_file

    def _exploding_parse(path: str) -> dict:
        if "bad.rpy" in path:
            raise RuntimeError("simulated parse failure")
        return _real_parse(path)

    monkeypatch.setattr(project_mod, "parse_file", _exploding_parse)

    with caplog.at_level(logging.WARNING, logger="renpy_analyzer.project"):
        model = load_project(str(tmp_path))

    # Good file should still load
    assert len(model.labels) >= 1
    # Bad file should produce a warning
    assert any("bad.rpy" in r.message for r in caplog.records)
