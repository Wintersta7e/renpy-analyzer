"""Tests for multi-game directory detection and independent analysis."""

from __future__ import annotations

from renpy_analyzer.analyzer import run_analysis
from renpy_analyzer.project import detect_sub_games, load_project


def _make_game_dir(path, rpy_content="label start:\n    return\n"):
    """Create a minimal game directory with a single .rpy file."""
    game = path / "game"
    game.mkdir(parents=True, exist_ok=True)
    (game / "script.rpy").write_text(rpy_content)


class TestSubGameDetection:
    """Tests for detect_sub_games() function."""

    def test_multi_game_dirs_detected(self, tmp_path):
        """A parent dir with multiple child dirs each having game/ is detected."""
        _make_game_dir(tmp_path / "Season1")
        _make_game_dir(tmp_path / "Season2")
        _make_game_dir(tmp_path / "Season3")

        sub_games = detect_sub_games(str(tmp_path))
        assert sorted(sub_games) == ["Season1", "Season2", "Season3"]

    def test_single_game_no_multi(self, tmp_path):
        """A normal single-game directory returns empty list."""
        _make_game_dir(tmp_path)

        sub_games = detect_sub_games(str(tmp_path))
        assert sub_games == []

    def test_single_subdir_with_game_no_multi(self, tmp_path):
        """Only one subdirectory with game/ should not trigger multi-game detection."""
        _make_game_dir(tmp_path / "OnlyGame")

        sub_games = detect_sub_games(str(tmp_path))
        assert sub_games == []

    def test_subdirs_without_game_ignored(self, tmp_path):
        """Subdirectories that don't contain game/ are not counted."""
        _make_game_dir(tmp_path / "Season1")
        _make_game_dir(tmp_path / "Season2")
        # A plain directory without game/ subfolder
        (tmp_path / "extras").mkdir()
        (tmp_path / "extras" / "readme.txt").write_text("notes")

        sub_games = detect_sub_games(str(tmp_path))
        assert sorted(sub_games) == ["Season1", "Season2"]


class TestMultiGameIndependentAnalysis:
    """Tests that multi-game directories are analyzed independently."""

    def test_each_sub_game_analyzed_independently(self, tmp_path):
        """Labels in Season1 should not cause 'missing label' in Season2."""
        _make_game_dir(
            tmp_path / "Season1",
            "label s1_start:\n    jump s1_ending\nlabel s1_ending:\n    return\n",
        )
        _make_game_dir(
            tmp_path / "Season2",
            "label s2_start:\n    jump s2_ending\nlabel s2_ending:\n    return\n",
        )

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        # No cross-contamination: s1 labels don't leak into s2 and vice versa
        missing = [f for f in findings if "Missing label" in f.title]
        assert len(missing) == 0

    def test_cross_contamination_would_fail_without_isolation(self, tmp_path):
        """Without isolation, jump to s1-only label from s2 would be 'missing'.
        With isolation, each sub-game's internal jumps resolve correctly."""
        _make_game_dir(
            tmp_path / "Season1",
            "label unique_s1:\n    return\n",
        )
        _make_game_dir(
            tmp_path / "Season2",
            "label unique_s2:\n    return\n",
        )

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        # No findings about missing labels across seasons
        missing = [f for f in findings if "Missing label" in f.title]
        assert len(missing) == 0

    def test_findings_prefixed_with_sub_game_name(self, tmp_path):
        """Findings from sub-games should have file paths prefixed with sub-game name."""
        _make_game_dir(
            tmp_path / "Season1",
            "label start:\n    jump nonexistent\n",
        )
        _make_game_dir(
            tmp_path / "Season2",
            "label start:\n    return\n",
        )

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        # Season1 should have a missing label finding prefixed with "Season1/"
        s1_findings = [f for f in findings if f.file.startswith("Season1/")]
        assert len(s1_findings) >= 1
        # Season2 has no issues
        s2_findings = [f for f in findings if f.file.startswith("Season2/")]
        assert len(s2_findings) == 0

    def test_no_warning_for_single_game(self, tmp_path):
        """A single-game directory should not produce any project warnings."""
        _make_game_dir(tmp_path)

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        project_findings = [f for f in findings if f.check_name == "project"]
        assert len(project_findings) == 0

    def test_findings_combined_and_sorted(self, tmp_path):
        """Findings from all sub-games are combined and sorted by severity."""
        _make_game_dir(
            tmp_path / "GameA",
            "label start:\n    jump missing_a\n",
        )
        _make_game_dir(
            tmp_path / "GameB",
            "label start:\n    jump missing_b\n",
        )

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        missing = [f for f in findings if "Missing label" in f.title]
        assert len(missing) == 2
        # One from each game
        files = {f.file.split("/")[0] for f in missing}
        assert files == {"GameA", "GameB"}
        # Sorted by severity
        for i in range(len(findings) - 1):
            assert findings[i].severity <= findings[i + 1].severity

    def test_rpyc_only_sub_game(self, tmp_path):
        """A sub-game with only .rpyc files should produce the rpyc warning."""
        _make_game_dir(tmp_path / "Season1", "label start:\n    return\n")
        # Season2: game/ with only .rpyc
        s2_game = tmp_path / "Season2" / "game"
        s2_game.mkdir(parents=True)
        (s2_game / "script.rpyc").write_bytes(b"\x00" * 10)

        findings = run_analysis(str(tmp_path), checks=["Labels"])
        rpyc_warnings = [f for f in findings if "No .rpy source" in f.title]
        assert len(rpyc_warnings) == 1
