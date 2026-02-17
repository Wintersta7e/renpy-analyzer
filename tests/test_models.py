"""Smoke tests for data models."""
from renpy_analyzer.models import (
    Severity, Label, Jump, Variable, Menu, MenuChoice,
    Finding, ProjectModel,
)


def test_severity_ordering():
    assert Severity.CRITICAL < Severity.HIGH < Severity.MEDIUM < Severity.LOW < Severity.STYLE


def test_project_model_defaults():
    pm = ProjectModel(root_dir="/tmp/test")
    assert pm.labels == []
    assert pm.jumps == []
    assert pm.variables == []


def test_finding_creation():
    f = Finding(
        severity=Severity.CRITICAL,
        check_name="labels",
        title="Missing label",
        description="Jump target 'foo' not defined",
        file="script.rpy",
        line=42,
    )
    assert f.severity == Severity.CRITICAL
    assert f.suggestion == ""
