"""Check for translation issues: duplicate entries, incomplete coverage."""

from __future__ import annotations

from collections import defaultdict

from ..models import Finding, ProjectModel, Severity


def check(project: ProjectModel) -> list[Finding]:
    findings: list[Finding] = []

    if not project.translations:
        return findings

    # Group by language
    by_language: dict[str, list] = defaultdict(list)
    for t in project.translations:
        by_language[t.language].append(t)

    # Check for duplicate translations (same language + same string_id)
    for lang, blocks in by_language.items():
        seen: dict[str, list] = {}
        for t in blocks:
            seen.setdefault(t.string_id, []).append(t)
        for string_id, entries in seen.items():
            if len(entries) > 1:
                first = entries[0]
                locations = ", ".join(f"{e.file}:{e.line}" for e in entries)
                findings.append(
                    Finding(
                        severity=Severity.MEDIUM,
                        check_name="translations",
                        title=f"Duplicate translation '{string_id}' ({lang})",
                        description=(
                            f"Translation for '{string_id}' in language '{lang}' "
                            f"is defined {len(entries)} times: {locations}. "
                            f"Only the last definition will be used."
                        ),
                        file=first.file,
                        line=first.line,
                        suggestion="Remove duplicate translation blocks.",
                    )
                )

    # Incomplete coverage (only when 2+ languages exist)
    languages = sorted(by_language.keys())
    if len(languages) >= 2:
        # Collect all string_ids per language
        ids_by_lang: dict[str, set[str]] = {}
        for lang in languages:
            ids_by_lang[lang] = {t.string_id for t in by_language[lang]}

        all_ids = set()
        for ids in ids_by_lang.values():
            all_ids |= ids

        for lang in languages:
            missing = all_ids - ids_by_lang[lang]
            if missing:
                # Report first missing ID as representative
                sample = sorted(missing)[0]
                # Find a file where this language has translations
                first_block = by_language[lang][0]
                findings.append(
                    Finding(
                        severity=Severity.LOW,
                        check_name="translations",
                        title=f"Incomplete translations for '{lang}'",
                        description=(
                            f"Language '{lang}' is missing {len(missing)} translation(s) "
                            f"present in other languages (e.g. '{sample}')."
                        ),
                        file=first_block.file,
                        line=first_block.line,
                        suggestion=f"Add missing 'translate {lang} ...:' blocks.",
                    )
                )

    return findings
