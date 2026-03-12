"""Tests for bridge_worker._drain_parse_errors — parse error accumulation fix."""

from __future__ import annotations

from types import SimpleNamespace

from renpy_analyzer.bridge_worker import _drain_parse_errors


def _make_mock_renpy(errors: list[str], has_get_fn: bool = True) -> SimpleNamespace:
    """Create a mock renpy module with parser.parse_errors."""
    parser = SimpleNamespace()
    parser.parse_errors = list(errors)

    if has_get_fn:
        # Simulate get_parse_errors() which returns and clears the list
        def get_parse_errors():
            result = list(parser.parse_errors)
            parser.parse_errors.clear()
            return result

        parser.get_parse_errors = get_parse_errors
    else:
        # Older SDK without get_parse_errors
        pass

    return SimpleNamespace(parser=parser)


def test_drain_with_get_fn():
    """get_parse_errors() should return errors and clear the list."""
    renpy = _make_mock_renpy(["error1", "error2"], has_get_fn=True)
    errors = _drain_parse_errors(renpy)
    assert errors == ["error1", "error2"]
    assert renpy.parser.parse_errors == []


def test_drain_without_get_fn():
    """Fallback should clear parse_errors manually for older SDKs."""
    renpy = _make_mock_renpy(["error1"], has_get_fn=False)
    errors = _drain_parse_errors(renpy)
    assert errors == ["error1"]
    assert renpy.parser.parse_errors == []


def test_drain_empty():
    """No errors should return empty list."""
    renpy = _make_mock_renpy([], has_get_fn=True)
    errors = _drain_parse_errors(renpy)
    assert errors == []


def test_drain_prevents_poisoning():
    """Draining after each file prevents error accumulation."""
    renpy = _make_mock_renpy([], has_get_fn=True)

    # Simulate file A producing an error
    renpy.parser.parse_errors.append("file_a error")
    errors_a = _drain_parse_errors(renpy)
    assert errors_a == ["file_a error"]

    # File B should have clean state
    errors_b = _drain_parse_errors(renpy)
    assert errors_b == []


def test_drain_defensive_clear_after_get_fn():
    """Even if get_parse_errors() doesn't clear, defensive clear handles it."""
    parser = SimpleNamespace()
    parser.parse_errors = ["leftover"]

    # Simulate a buggy get_parse_errors that returns but doesn't clear
    def buggy_get():
        return list(parser.parse_errors)  # Returns copy, never clears

    parser.get_parse_errors = buggy_get
    renpy = SimpleNamespace(parser=parser)

    errors = _drain_parse_errors(renpy)
    assert errors == ["leftover"]
    # Defensive clear should have emptied it regardless
    assert renpy.parser.parse_errors == []
