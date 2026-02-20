"""Tests for checks/translations.py — translation validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

from renpy_analyzer.checks.translations import check
from renpy_analyzer.models import (
    ProjectModel,
    Severity,
    TranslationBlock,
)
from renpy_analyzer.parser import parse_file


def _model(**kwargs) -> ProjectModel:
    return ProjectModel(root_dir="/test", **kwargs)


# --- Check logic tests ---


def test_duplicate_translation():
    model = _model(
        translations=[
            TranslationBlock(language="spanish", string_id="start_abc123", file="tl.rpy", line=1),
            TranslationBlock(language="spanish", string_id="start_abc123", file="tl.rpy", line=10),
        ],
    )
    findings = check(model)
    dups = [f for f in findings if f.severity == Severity.MEDIUM]
    assert len(dups) == 1
    assert "Duplicate" in dups[0].title


def test_no_duplicates_clean():
    model = _model(
        translations=[
            TranslationBlock(language="spanish", string_id="start_abc123", file="tl.rpy", line=1),
            TranslationBlock(language="spanish", string_id="start_def456", file="tl.rpy", line=10),
        ],
    )
    findings = check(model)
    assert len(findings) == 0


def test_empty_model():
    model = _model()
    findings = check(model)
    assert findings == []


def test_incomplete_coverage():
    model = _model(
        translations=[
            TranslationBlock(language="spanish", string_id="start_abc", file="tl_es.rpy", line=1),
            TranslationBlock(language="spanish", string_id="start_def", file="tl_es.rpy", line=5),
            TranslationBlock(language="french", string_id="start_abc", file="tl_fr.rpy", line=1),
            # french is missing start_def
        ],
    )
    findings = check(model)
    incomplete = [f for f in findings if f.severity == Severity.LOW]
    assert len(incomplete) == 1
    assert "french" in incomplete[0].title


def test_single_language_no_coverage_warning():
    """With only one language, incomplete coverage check should not fire."""
    model = _model(
        translations=[
            TranslationBlock(language="spanish", string_id="start_abc", file="tl.rpy", line=1),
        ],
    )
    findings = check(model)
    assert len(findings) == 0


def test_same_id_different_languages_ok():
    """Same string_id in different languages is normal, not a duplicate."""
    model = _model(
        translations=[
            TranslationBlock(language="spanish", string_id="start_abc", file="tl_es.rpy", line=1),
            TranslationBlock(language="french", string_id="start_abc", file="tl_fr.rpy", line=1),
        ],
    )
    findings = check(model)
    assert len(findings) == 0


# --- Parser extraction tests ---


def _write_rpy(tmp_path: Path, content: str) -> str:
    f = tmp_path / "test.rpy"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


def test_parser_translate_block(tmp_path):
    path = _write_rpy(
        tmp_path,
        """\
        translate spanish start_abc123:
            mc "Hola mundo"
    """,
    )
    result = parse_file(path)
    assert len(result["translations"]) == 1
    assert result["translations"][0].language == "spanish"
    assert result["translations"][0].string_id == "start_abc123"
