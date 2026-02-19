"""Logging configuration for Ren'Py Analyzer."""

from __future__ import annotations

import logging
import sys


def setup_logging(
    verbose: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure the ``renpy_analyzer`` logger hierarchy.

    Parameters
    ----------
    verbose:
        If *True*, set the root logger level to DEBUG; otherwise INFO.
    log_file:
        If given, also write log output to this file path.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("renpy_analyzer")
    logger.setLevel(level)

    # Avoid duplicate handlers when called more than once (e.g. tests)
    if logger.handlers:
        return

    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s")

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
