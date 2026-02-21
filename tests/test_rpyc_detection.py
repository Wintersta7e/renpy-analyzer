"""Tests for compiled-only (.rpyc) game detection."""

from __future__ import annotations

import os
import tempfile

from renpy_analyzer.analyzer import run_analysis
from renpy_analyzer.models import ProjectModel, Severity


class TestRpycOnlyDetection:
    """Test that rpyc-only projects emit a warning finding."""

    def test_rpyc_only_flag_triggers_warning(self) -> None:
        """A ProjectModel with has_rpyc_only=True causes the analyzer to emit a warning."""
        # Create a temp dir with only .rpyc files (no .rpy files)
        with tempfile.TemporaryDirectory() as tmpdir:
            game_dir = os.path.join(tmpdir, "game")
            os.makedirs(game_dir)
            # Create some .rpyc files
            for name in ["script.rpyc", "options.rpyc", "gui.rpyc"]:
                open(os.path.join(game_dir, name), "wb").close()

            findings = run_analysis(tmpdir)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.severity == Severity.MEDIUM
        assert finding.check_name == "project"
        assert "No .rpy source files found" in finding.title
        assert ".rpyc" in finding.description

    def test_rpyc_only_finding_fields(self) -> None:
        """The rpyc-only finding has the expected field values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            game_dir = os.path.join(tmpdir, "game")
            os.makedirs(game_dir)
            open(os.path.join(game_dir, "script.rpyc"), "wb").close()

            findings = run_analysis(tmpdir)

        finding = findings[0]
        assert finding.file == ""
        assert finding.line == 0
        assert "decompile" in finding.suggestion.lower() or "uncompiled" in finding.suggestion.lower()

    def test_normal_project_no_rpyc_warning(self) -> None:
        """A project with .rpy files does NOT get the rpyc-only warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            game_dir = os.path.join(tmpdir, "game")
            os.makedirs(game_dir)
            # Create a .rpy file with valid content
            with open(os.path.join(game_dir, "script.rpy"), "w") as f:
                f.write("label start:\n    return\n")

            findings = run_analysis(tmpdir)

        rpyc_warnings = [f for f in findings if f.check_name == "project" and "rpyc" in f.description.lower()]
        assert len(rpyc_warnings) == 0

    def test_empty_dir_no_rpyc_warning(self) -> None:
        """An empty directory (no .rpy or .rpyc files) does NOT get the rpyc-only warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            game_dir = os.path.join(tmpdir, "game")
            os.makedirs(game_dir)

            findings = run_analysis(tmpdir)

        rpyc_warnings = [f for f in findings if f.check_name == "project"]
        assert len(rpyc_warnings) == 0

    def test_model_has_rpyc_only_default_false(self) -> None:
        """ProjectModel.has_rpyc_only defaults to False."""
        model = ProjectModel(root_dir="/tmp/test")
        assert model.has_rpyc_only is False
