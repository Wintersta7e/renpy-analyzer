"""Tests for multi-game directory detection and warning."""

from __future__ import annotations

from renpy_analyzer.analyzer import run_analysis
from renpy_analyzer.project import load_project


def _make_game_dir(path, rpy_content="label start:\n    return\n"):
    """Create a minimal game directory with a single .rpy file."""
    game = path / "game"
    game.mkdir(parents=True, exist_ok=True)
    (game / "script.rpy").write_text(rpy_content)


class TestMultiGameDetection:
    """Tests for ProjectModel.multi_game_dirs population in load_project."""

    def test_multi_game_dirs_detected(self, tmp_path):
        """A parent dir with multiple child dirs each having game/ is detected."""
        _make_game_dir(tmp_path / "Season1")
        _make_game_dir(tmp_path / "Season2")
        _make_game_dir(tmp_path / "Season3")

        model = load_project(str(tmp_path))
        assert sorted(model.multi_game_dirs) == ["Season1", "Season2", "Season3"]

    def test_single_game_no_multi(self, tmp_path):
        """A normal single-game directory has empty multi_game_dirs."""
        _make_game_dir(tmp_path)

        model = load_project(str(tmp_path))
        assert model.multi_game_dirs == []

    def test_single_subdir_with_game_no_multi(self, tmp_path):
        """Only one subdirectory with game/ should not trigger multi-game detection."""
        _make_game_dir(tmp_path / "OnlyGame")

        model = load_project(str(tmp_path))
        assert model.multi_game_dirs == []

    def test_subdirs_without_game_ignored(self, tmp_path):
        """Subdirectories that don't contain game/ are not counted."""
        _make_game_dir(tmp_path / "Season1")
        _make_game_dir(tmp_path / "Season2")
        # A plain directory without game/ subfolder
        (tmp_path / "extras").mkdir()
        (tmp_path / "extras" / "readme.txt").write_text("notes")

        model = load_project(str(tmp_path))
        assert sorted(model.multi_game_dirs) == ["Season1", "Season2"]


class TestMultiGameWarningFinding:
    """Tests that the analyzer emits a warning finding for multi-game dirs."""

    def test_warning_emitted(self, tmp_path):
        """When multi_game_dirs is populated, a MEDIUM finding is emitted."""
        _make_game_dir(tmp_path / "GameA")
        _make_game_dir(tmp_path / "GameB")

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        multi_findings = [
            f for f in findings
            if f.check_name == "project" and "Multiple game projects" in f.title
        ]
        assert len(multi_findings) == 1
        f = multi_findings[0]
        assert f.severity.name == "MEDIUM"
        assert "GameA" in f.description
        assert "GameB" in f.description
        assert "false positives" in f.description

    def test_no_warning_for_single_game(self, tmp_path):
        """A single-game directory should produce no multi-game warning."""
        _make_game_dir(tmp_path)

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        multi_findings = [
            f for f in findings
            if f.check_name == "project" and "Multiple game projects" in f.title
        ]
        assert len(multi_findings) == 0

    def test_warning_lists_truncated_for_many_dirs(self, tmp_path):
        """When there are more than 5 game dirs, the list is truncated with '...'."""
        for i in range(7):
            _make_game_dir(tmp_path / f"Game{i:02d}")

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        multi_findings = [
            f for f in findings
            if f.check_name == "project" and "Multiple game projects" in f.title
        ]
        assert len(multi_findings) == 1
        assert "..." in multi_findings[0].description
        assert "7 separate game projects" in multi_findings[0].description
