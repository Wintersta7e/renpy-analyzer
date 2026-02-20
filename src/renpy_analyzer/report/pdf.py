"""Styled PDF report generator using PyMuPDF — Midnight theme.

Produces a professional A4 report with:
- Dark midnight background (#0D1B2A) on all pages
- Measure-first architecture: every component measures its exact height
  before drawing, eliminating overlap and orphaned-header bugs
- Findings grouped by check category and deduplicated by title
- Tiered display: full cards for CRITICAL/HIGH, compact for MEDIUM,
  table rows for LOW/STYLE
- Vibrant severity badges against the dark background
- Clickable table of contents + PDF bookmark sidebar
- Page numbers in footer
"""

from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

import fitz  # PyMuPDF

from ..models import Finding, Severity

# ---------------------------------------------------------------------------
# Hex helper
# ---------------------------------------------------------------------------


def _hex(h: str) -> tuple[float, float, float]:
    """Convert '#RRGGBB' to an (r, g, b) float tuple for PyMuPDF."""
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


# ---------------------------------------------------------------------------
# Midnight colour palette
# ---------------------------------------------------------------------------

_C = {
    "page_bg": _hex("#0D1B2A"),
    "card_bg": _hex("#1B2838"),
    "card_border": _hex("#2A3A4E"),
    "section_bg": _hex("#152232"),
    "loc_bg": _hex("#0F1D2D"),
    "table_hdr_bg": _hex("#1B2838"),
    "table_alt": _hex("#132030"),
    "text": _hex("#E0E6ED"),
    "text2": _hex("#8899AA"),
    "text3": _hex("#5A6A7A"),
    "accent": _hex("#2A3A4E"),
    "white": (1.0, 1.0, 1.0),
    "banner_top": _hex("#0D1B2A"),
    "banner_bot": _hex("#091520"),
    "suggest_bg": _hex("#122218"),
    "suggest_text": _hex("#5ABF7B"),
}

_SEV_BG = {
    Severity.CRITICAL: _hex("#FF4757"),
    Severity.HIGH: _hex("#FF8C42"),
    Severity.MEDIUM: _hex("#FFCB47"),
    Severity.LOW: _hex("#2ED573"),
    Severity.STYLE: _hex("#7C8A96"),
}

_SEV_FG = {
    Severity.CRITICAL: _C["white"],
    Severity.HIGH: _C["white"],
    Severity.MEDIUM: _C["page_bg"],
    Severity.LOW: _C["white"],
    Severity.STYLE: _C["white"],
}

_CATEGORY_ORDER = ["Labels", "Variables", "Logic", "Menus", "Assets", "Characters", "Flow"]

_CHECK_TO_CATEGORY = {
    "labels": "Labels",
    "variables": "Variables",
    "logic": "Logic",
    "menus": "Menus",
    "assets": "Assets",
    "characters": "Characters",
    "flow": "Flow",
}

# ---------------------------------------------------------------------------
# Layout constants (A4 = 595 x 842 pt)
# ---------------------------------------------------------------------------

_PAGE_W: float = 595
_PAGE_H: float = 842
_ML: float = 50  # margin left
_MR: float = 50  # margin right
_MT: float = 55  # margin top
_MB: float = 50  # margin bottom
_CW: float = _PAGE_W - _ML - _MR  # 495  content width

# Fonts (Base-14)
_F = "helv"  # Helvetica
_FB = "hebo"  # Helvetica-Bold
_FM = "cour"  # Courier

# Font objects for measuring (lazy-initialized)
_FONT_CACHE: dict[str, fitz.Font] = {}


def _get_font(name: str) -> fitz.Font:
    if name not in _FONT_CACHE:
        _FONT_CACHE[name] = fitz.Font(name)
    return _FONT_CACHE[name]


def _tw(text: str, font: str, size: float) -> float:
    """Text width in points."""
    return float(_get_font(font).text_length(text, fontsize=size))


def _wrap(text: str, max_w: float, font: str, size: float) -> list[str]:
    """Word-wrap *text* to fit within *max_w* points."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if _tw(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


# Location layout
_LOC_FS = 7.5
_LOC_LH = 11
_LOC_COL_W = (_CW - 28) / 2

_MAX_LOCS_FULL = 20
_MAX_LOCS_COMPACT = 10

# ---------------------------------------------------------------------------
# Grouped finding model
# ---------------------------------------------------------------------------


@dataclass
class _GroupedFinding:
    severity: Severity
    check_name: str
    title: str
    description: str
    suggestion: str
    locations: list[tuple[str, int]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.locations)


def _group_findings(
    findings: list[Finding],
    game_path: str,
) -> dict[str, list[_GroupedFinding]]:
    """Group findings by category then deduplicate by title within each."""
    buckets: dict[tuple[str, str], _GroupedFinding] = {}
    for f in findings:
        cat = _CHECK_TO_CATEGORY.get(f.check_name, f.check_name.title())
        key = (cat, f.title)
        rel_file = f.file
        if game_path and rel_file.startswith(game_path):
            rel_file = os.path.relpath(rel_file, game_path)
        if key not in buckets:
            buckets[key] = _GroupedFinding(
                severity=f.severity,
                check_name=f.check_name,
                title=f.title,
                description=f.description,
                suggestion=f.suggestion,
                locations=[(rel_file, f.line)],
            )
        else:
            buckets[key].locations.append((rel_file, f.line))

    for g in buckets.values():
        g.locations.sort(key=lambda loc: (loc[0], loc[1]))

    by_cat: dict[str, list[_GroupedFinding]] = {}
    for (cat, _), group in buckets.items():
        by_cat.setdefault(cat, []).append(group)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda g: (g.severity, g.title))

    return by_cat


# ---------------------------------------------------------------------------
# Measure helpers — compute exact heights without drawing
# ---------------------------------------------------------------------------


def _loc_block_h(n: int, two_col: bool = True, overflow: bool = False) -> float:
    """Height of a location block with *n* entries."""
    if n == 0:
        return 0
    rows = math.ceil(n / 2) if two_col else n
    if overflow:
        rows += 1
    return rows * _LOC_LH + 6


def _measure_full_card(g: _GroupedFinding) -> float:
    """Exact height for a CRITICAL/HIGH full card."""
    inner_w = _CW - 28
    title_lines = _wrap(g.title, _CW - 100, _FB, 11)
    desc_lines = _wrap(g.description, inner_w, _F, 9.5)
    sugg_lines = _wrap(g.suggestion, inner_w - 16, _F, 9) if g.suggestion else []

    capped = min(len(g.locations), _MAX_LOCS_FULL)
    overflow = len(g.locations) - capped
    loc_h = _loc_block_h(capped, overflow=overflow > 0)

    h: float = 16  # top pad + badge line
    h += len(title_lines) * 14  # title
    h += 6  # gap
    h += len(desc_lines) * 13  # description
    if sugg_lines:
        h += 10  # gap + "Suggestion:" label
        h += 12  # label line
        h += len(sugg_lines) * 12  # suggestion body
    h += 10  # gap before locations
    h += 12  # "Locations:" label
    h += loc_h  # location rows
    h += 10  # bottom pad
    return max(h, 60)


def _measure_compact_card(g: _GroupedFinding) -> float:
    """Exact height for a MEDIUM compact card."""
    inner_w = _CW - 24
    title_lines = _wrap(g.title, _CW - 100, _FB, 10)
    desc_lines = _wrap(g.description, inner_w, _F, 9)
    sugg_lines = _wrap(g.suggestion, inner_w - 16, _F, 8.5) if g.suggestion else []

    capped = min(len(g.locations), _MAX_LOCS_COMPACT)
    overflow = len(g.locations) - capped
    loc_h = _loc_block_h(capped, overflow=overflow > 0)

    h: float = 14  # top pad + badge
    h += len(title_lines) * 13  # title
    h += 4  # gap
    h += len(desc_lines) * 12  # full description
    if sugg_lines:
        h += 8  # gap + "Suggestion:" label
        h += 12  # label line
        h += len(sugg_lines) * 11  # suggestion body
    h += 8  # gap before locations
    h += 12  # "Locations:" label
    h += loc_h  # locations
    h += 8  # bottom pad
    return max(h, 44)


def _measure_table_row(g: _GroupedFinding) -> float:
    """Exact height for a LOW/STYLE table row."""
    return 28  # title + location line + padding


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------


class _PDFBuilder:
    """Manages page creation, cursor tracking, and content rendering."""

    def __init__(self, game_name: str, game_path: str) -> None:
        self.doc = fitz.open()
        self.game_name = game_name
        self.game_path = game_path
        self.page: fitz.Page | None = None
        self.page_num = 0
        self.y = _MT
        self._footer_drawn = False
        self._toc_targets: list[tuple[int, float, str, int]] = []
        self._bookmark_toc: list[list] = []

    # -- page management ----------------------------------------------------

    def new_page(self) -> fitz.Page:
        if self.page is not None and not self._footer_drawn:
            self._draw_footer()
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.page_num += 1
        self.y = _MT
        self._footer_drawn = False
        # Midnight background
        self.page.draw_rect(
            fitz.Rect(0, 0, _PAGE_W, _PAGE_H),
            fill=_C["page_bg"],
            color=None,
        )
        return self.page

    def _avail(self) -> float:
        return _PAGE_H - _MB - self.y

    def ensure_space(self, needed: float) -> None:
        if self._avail() < needed:
            self.new_page()

    # -- footer -------------------------------------------------------------

    def _draw_footer(self) -> None:
        if self.page is None or self._footer_drawn:
            return
        self._footer_drawn = True
        text = f"Page {self.page_num}"
        tw = _tw(text, _F, 8)
        self.page.insert_text(
            fitz.Point((_PAGE_W - tw) / 2, _PAGE_H - 25),
            text,
            fontsize=8,
            fontname=_F,
            color=_C["text3"],
        )

    # -- primitive drawing helpers ------------------------------------------

    def _text(self, x: float, text: str, font: str = _F, size: float = 10, color: tuple | None = None) -> float:
        """Insert text at (x, self.y). Returns text width."""
        if color is None:
            color = _C["text"]
        self.page.insert_text(
            fitz.Point(x, self.y),
            text,
            fontsize=size,
            fontname=font,
            color=color,
        )
        return _tw(text, font, size)

    def _rect(self, rect: fitz.Rect, fill=None, border=None, width: float = 0.5, radius: float | None = None) -> None:
        kw: dict = {"fill": fill, "color": border, "width": width}
        if radius is not None:
            kw["radius"] = radius
        self.page.draw_rect(rect, **kw)

    def _badge(
        self, x: float, y: float, text: str, bg: tuple, fg: tuple, size: float = 8, hpad: float = 6, vpad: float = 3
    ) -> float:
        """Draw a rounded badge. Returns badge width."""
        tw = _tw(text, _FB, size)
        bw = tw + hpad * 2
        bh = size + vpad * 2
        self._rect(
            fitz.Rect(x, y - bh + vpad, x + bw, y + vpad),
            fill=bg,
            border=None,
            radius=0.25,
        )
        self.page.insert_text(
            fitz.Point(x + hpad, y),
            text,
            fontsize=size,
            fontname=_FB,
            color=fg,
        )
        return bw

    def _rule(self) -> None:
        """Draw a horizontal divider at self.y."""
        self.page.draw_line(
            fitz.Point(_ML, self.y),
            fitz.Point(_PAGE_W - _MR, self.y),
            color=_C["accent"],
            width=0.6,
        )

    # -- location rendering -------------------------------------------------

    def _fmt_loc(self, f: str, ln: int) -> str:
        return f"{f}:{ln}"

    def _draw_locs_2col(self, locs: list[tuple[str, int]], left_x: float, max_n: int | None = None) -> None:
        """Draw locations in 2-column layout starting at self.y."""
        show = locs if max_n is None else locs[:max_n]
        overflow = len(locs) - len(show)
        col_w = _LOC_COL_W
        col2_x = left_x + col_w + 8

        for i, (f, ln) in enumerate(show):
            s = self._fmt_loc(f, ln)
            while _tw(s, _FM, _LOC_FS) > col_w - 4 and len(s) > 20:
                s = s[:-4] + "..."
            x = left_x if i % 2 == 0 else col2_x
            self.page.insert_text(
                fitz.Point(x, self.y),
                s,
                fontsize=_LOC_FS,
                fontname=_FM,
                color=_C["text2"],
            )
            if i % 2 == 1 or i == len(show) - 1:
                self.y += _LOC_LH

        if overflow > 0:
            more = f"... and {overflow} more location{'s' if overflow != 1 else ''}"
            self.page.insert_text(
                fitz.Point(left_x, self.y),
                more,
                fontsize=_LOC_FS,
                fontname=_F,
                color=_C["text3"],
            )
            self.y += _LOC_LH

    def _draw_locs_inline(self, locs: list[tuple[str, int]], left_x: float, max_n: int = 3) -> None:
        """Draw locations inline on a single line (for table rows)."""
        show = locs[:max_n]
        overflow = len(locs) - len(show)
        parts = [self._fmt_loc(f, ln) for f, ln in show]
        if overflow > 0:
            parts.append(f"and {overflow} more")
        text = "  |  ".join(parts)
        max_w = _CW - (left_x - _ML) - 10
        while _tw(text, _FM, 7) > max_w and len(text) > 30:
            text = text[:-4] + "..."
        self.page.insert_text(
            fitz.Point(left_x, self.y),
            text,
            fontsize=7,
            fontname=_FM,
            color=_C["text3"],
        )

    # ======================================================================
    # HIGH-LEVEL SECTIONS
    # ======================================================================

    # -- Title page ---------------------------------------------------------

    def draw_title_page(self, findings: list[Finding]) -> None:
        self.new_page()

        # Full-width dark banner
        banner_h = 110
        self._rect(
            fitz.Rect(0, 0, _PAGE_W, banner_h),
            fill=_C["banner_bot"],
            border=None,
        )
        # Lighter top portion for gradient effect
        self._rect(
            fitz.Rect(0, 0, _PAGE_W, banner_h * 0.6),
            fill=_C["banner_top"],
            border=None,
        )

        # Game name  (baseline at y=50, ascent ~16pt for size 22)
        self.y = 50
        self._text(_ML, self.game_name, font=_FB, size=22, color=_C["white"])

        # Subtitle  (baseline at y=74)
        self.y = 74
        self._text(_ML, "Ren'Py Analyzer Report", font=_F, size=12, color=_C["text2"])

        # Date  (baseline at y=94)
        self.y = 94
        date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
        self._text(_ML, date_str, font=_F, size=9, color=_C["text3"])

        # -- Below banner --
        self.y = banner_h + 22  # y = 132
        if self.game_path:
            self._text(_ML, "Project path:", font=_FB, size=9, color=_C["text2"])
            self.y += 14
            dp = self.game_path
            while _tw(dp, _FM, 8) > _CW and len(dp) > 40:
                dp = "..." + dp[4:]
            self._text(_ML, dp, font=_FM, size=8, color=_C["text3"])
            self.y += 22

        # -- Summary heading --
        self.y += 8
        self._text(_ML, "Summary", font=_FB, size=18, color=_C["white"])
        self.y += 8
        self._rule()
        # 40pt text ascent is ~29pt, so we need baseline at least 30pt below the rule
        self.y += 44

        # Big total number  (40pt bold — ascent ~29pt above baseline)
        sev_counts = Counter(f.severity for f in findings)
        total = len(findings)
        self._text(_ML, str(total), font=_FB, size=40, color=_C["white"])
        total_w = _tw(str(total), _FB, 40)
        # "Total Findings" vertically centred with the big number
        # 40pt ascent ~29pt, so visual centre is at baseline - 14
        # 14pt ascent ~10pt, so we need its baseline at big_baseline - 14 + 5 = -9
        save_y = self.y
        self.y -= 9
        self._text(_ML + total_w + 12, "Total Findings", font=_F, size=14, color=_C["text2"])
        # Advance past the big number: 40pt descent ~11pt, badges extend
        # ~15pt above their baseline, so need baseline + 11 + 15 + gap
        self.y = save_y + 32

        # Severity badges row
        x = _ML
        for sev in Severity:
            c = sev_counts.get(sev, 0)
            label = f"{sev.name}  {c}"
            bw = self._badge(x, self.y, label, bg=_SEV_BG[sev], fg=_SEV_FG[sev], size=10, hpad=10, vpad=5)
            x += bw + 12
        self.y += 30

        # -- Category breakdown table --
        self._text(_ML, "Findings by Category", font=_FB, size=14, color=_C["white"])
        self.y += 20

        cat_counts: dict[str, Counter] = {}
        for f in findings:
            cat = _CHECK_TO_CATEGORY.get(f.check_name, f.check_name.title())
            cat_counts.setdefault(cat, Counter())[f.severity] += 1

        label_col_w = 130
        sev_col_w = 65
        total_col_x = _ML + label_col_w + len(Severity) * sev_col_w

        # Header row — draw rect first, then all text at same baseline
        row_h = 18
        hdr_top = self.y - 2
        self._rect(
            fitz.Rect(_ML, hdr_top, _PAGE_W - _MR, hdr_top + row_h),
            fill=_C["table_hdr_bg"],
            border=None,
        )
        hdr_baseline = hdr_top + 13  # 13pt down inside 18pt row
        self.y = hdr_baseline
        self._text(_ML + 5, "Category", font=_FB, size=9, color=_C["white"])
        for i, sev in enumerate(Severity):
            self.y = hdr_baseline
            self._text(_ML + label_col_w + i * sev_col_w + 5, sev.name, font=_FB, size=8, color=_C["white"])
        self.y = hdr_baseline
        self._text(total_col_x + 5, "TOTAL", font=_FB, size=8, color=_C["white"])
        self.y = hdr_top + row_h

        # Data rows
        for cat in _CATEGORY_ORDER:
            counts = cat_counts.get(cat, Counter())
            row_total = sum(counts.values())
            if row_total == 0:
                continue
            row_top = self.y
            # Alternating row bg (every other visible row)
            self._rect(
                fitz.Rect(_ML, row_top, _PAGE_W - _MR, row_top + row_h),
                fill=_C["table_alt"] if (row_top // row_h) % 2 == 0 else _C["page_bg"],
                border=None,
            )
            baseline = row_top + 13
            self.y = baseline
            self._text(_ML + 5, cat, font=_F, size=9, color=_C["text"])
            for i, sev in enumerate(Severity):
                c = counts.get(sev, 0)
                if c > 0:
                    self.y = baseline
                    self._text(_ML + label_col_w + i * sev_col_w + 5, str(c), font=_F, size=9, color=_SEV_BG[sev])
            self.y = baseline
            self._text(total_col_x + 5, str(row_total), font=_FB, size=9, color=_C["white"])
            self.y = row_top + row_h
            # Subtle divider
            self.page.draw_line(
                fitz.Point(_ML, self.y),
                fitz.Point(_PAGE_W - _MR, self.y),
                color=_C["accent"],
                width=0.3,
            )

        # Unique count note
        self.y += 14
        unique = len({f.title for f in findings})
        note = f"{total} total findings condensed into {unique} unique issues in this report."
        self._text(_ML, note, font=_F, size=9, color=_C["text2"])

        self._draw_footer()

    # -- TOC page -----------------------------------------------------------

    def draw_toc_page(self, categories: list[str]) -> int:
        self.new_page()
        toc_page_idx = self.page_num - 1

        self.y = _MT + 5
        self._text(_ML, "Table of Contents", font=_FB, size=20, color=_C["white"])
        self.y += 8
        self.page.draw_line(
            fitz.Point(_ML, self.y),
            fitz.Point(_PAGE_W - _MR, self.y),
            color=_C["accent"],
            width=1.2,
        )
        self.y += 25

        self._toc_start_y = self.y
        self._toc_page_idx = toc_page_idx

        self._draw_footer()
        return toc_page_idx

    def register_section(self, title: str, level: int = 1) -> None:
        page_idx = self.page_num - 1
        self._toc_targets.append((page_idx, self.y, title, level))
        self._bookmark_toc.append([level, title, self.page_num])

    # -- Section header -----------------------------------------------------

    def draw_section_header(
        self, title: str, finding_count: int, group_count: int, sev_color: tuple | None = None
    ) -> None:
        self.ensure_space(60)
        self.register_section(title, level=1)

        bar_h = 34
        # Section background
        self._rect(
            fitz.Rect(_ML, self.y - 6, _PAGE_W - _MR, self.y - 6 + bar_h),
            fill=_C["section_bg"],
            border=None,
            radius=0.02,
        )
        # Left accent bar (severity-tinted or white)
        accent = sev_color if sev_color else _C["white"]
        self._rect(
            fitz.Rect(_ML, self.y - 6, _ML + 4, self.y - 6 + bar_h),
            fill=accent,
            border=None,
        )

        # Title
        self.y += 4
        self._text(_ML + 14, title, font=_FB, size=16, color=_C["white"])

        # Count badge
        if finding_count == group_count:
            count_text = f"{finding_count} finding{'s' if finding_count != 1 else ''}"
        else:
            count_text = f"{finding_count} findings in {group_count} unique issues"
        title_w = _tw(title, _FB, 16)
        self._badge(
            _ML + 14 + title_w + 12,
            self.y,
            count_text,
            bg=_C["accent"],
            fg=_C["text2"],
            size=8,
        )
        self.y += bar_h - 2

    # ======================================================================
    # TIERED FINDING RENDERERS — Measure-first
    # ======================================================================

    # -- Full card (CRITICAL / HIGH) ----------------------------------------

    def draw_full_card(self, g: _GroupedFinding) -> None:
        sev_bg = _SEV_BG[g.severity]
        sev_fg = _SEV_FG[g.severity]
        inner_w = _CW - 28

        # ---- Measure ----
        card_h = _measure_full_card(g)
        self.ensure_space(card_h + 8)

        card_top = self.y - 4
        card_left = _ML
        card_right = _PAGE_W - _MR

        # ---- Draw card background (exact height known) ----
        self._rect(
            fitz.Rect(card_left, card_top, card_right, card_top + card_h),
            fill=_C["card_bg"],
            border=_C["card_border"],
            width=0.4,
            radius=0.02,
        )
        # Left accent
        self._rect(
            fitz.Rect(card_left, card_top, card_left + 4, card_top + card_h),
            fill=sev_bg,
            border=None,
        )

        inner_left = card_left + 14
        self.y = card_top + 16

        # Severity badge
        bw = self._badge(inner_left, self.y, g.severity.name, bg=sev_bg, fg=sev_fg, size=7, hpad=5, vpad=2)
        # Occurrence count
        if g.count > 1:
            self._badge(
                inner_left + bw + 8,
                self.y,
                f"{g.count} occurrences",
                bg=_C["accent"],
                fg=_C["text2"],
                size=7,
                hpad=4,
                vpad=2,
            )
        self.y += 14

        # Title
        for line in _wrap(g.title, _CW - 100, _FB, 11):
            self._text(inner_left, line, font=_FB, size=11, color=_C["white"])
            self.y += 14
        self.y += 2  # gap

        # Description
        for line in _wrap(g.description, inner_w, _F, 9.5):
            self._text(inner_left, line, font=_F, size=9.5, color=_C["text"])
            self.y += 13

        # Suggestion
        if g.suggestion:
            self.y += 4
            self._text(inner_left, "Suggestion:", font=_FB, size=8, color=_C["suggest_text"])
            self.y += 12
            sugg_lines = _wrap(g.suggestion, inner_w - 16, _F, 9)
            # Suggestion background
            sugg_h = len(sugg_lines) * 12 + 6
            self._rect(
                fitz.Rect(inner_left, self.y - 10, card_right - 14, self.y - 10 + sugg_h),
                fill=_C["suggest_bg"],
                border=None,
                radius=0.02,
            )
            for line in sugg_lines:
                self._text(inner_left + 8, line, font=_F, size=9, color=_C["suggest_text"])
                self.y += 12

        # Locations header
        self.y += 4
        self._text(inner_left, "Locations:", font=_FB, size=8, color=_C["text2"])
        self.y += 11

        # Location block background
        capped = min(len(g.locations), _MAX_LOCS_FULL)
        overflow = len(g.locations) - capped
        loc_h = _loc_block_h(capped, overflow=overflow > 0)
        if loc_h > 0:
            self._rect(
                fitz.Rect(inner_left - 4, self.y - 9, card_right - 10, self.y - 9 + loc_h),
                fill=_C["loc_bg"],
                border=None,
                radius=0.02,
            )
        self._draw_locs_2col(g.locations, inner_left, max_n=_MAX_LOCS_FULL)

        self.y = card_top + card_h + 8

    # -- Compact card (MEDIUM) ----------------------------------------------

    def draw_compact_card(self, g: _GroupedFinding) -> None:
        sev_bg = _SEV_BG[g.severity]
        sev_fg = _SEV_FG[g.severity]
        inner_w = _CW - 24

        card_h = _measure_compact_card(g)
        self.ensure_space(card_h + 6)

        card_top = self.y - 2
        card_left = _ML
        card_right = _PAGE_W - _MR

        # Card background
        self._rect(
            fitz.Rect(card_left, card_top, card_right, card_top + card_h),
            fill=_C["card_bg"],
            border=_C["card_border"],
            width=0.3,
            radius=0.02,
        )
        # Thin left accent
        self._rect(
            fitz.Rect(card_left, card_top, card_left + 3, card_top + card_h),
            fill=sev_bg,
            border=None,
        )

        inner_left = card_left + 12
        self.y = card_top + 13

        # Badge + count
        bw = self._badge(inner_left, self.y, g.severity.name, bg=sev_bg, fg=sev_fg, size=6.5, hpad=4, vpad=2)
        if g.count > 1:
            self._badge(
                inner_left + bw + 6, self.y, f"x{g.count}", bg=_C["accent"], fg=_C["text2"], size=6.5, hpad=3, vpad=2
            )
        self.y += 12

        # Title
        for line in _wrap(g.title, _CW - 100, _FB, 10):
            self._text(inner_left, line, font=_FB, size=10, color=_C["white"])
            self.y += 13
        self.y += 2

        # Full description
        for line in _wrap(g.description, inner_w, _F, 9):
            self._text(inner_left, line, font=_F, size=9, color=_C["text"])
            self.y += 12

        # Suggestion
        if g.suggestion:
            self.y += 3
            self._text(inner_left, "Suggestion:", font=_FB, size=8, color=_C["suggest_text"])
            self.y += 12
            sugg_lines = _wrap(g.suggestion, inner_w - 16, _F, 8.5)
            sugg_h = len(sugg_lines) * 11 + 6
            self._rect(
                fitz.Rect(inner_left, self.y - 10, card_right - 12, self.y - 10 + sugg_h),
                fill=_C["suggest_bg"],
                border=None,
                radius=0.02,
            )
            for line in sugg_lines:
                self._text(inner_left + 8, line, font=_F, size=8.5, color=_C["suggest_text"])
                self.y += 11

        # Locations header
        self.y += 3
        self._text(inner_left, "Locations:", font=_FB, size=8, color=_C["text2"])
        self.y += 11

        # Location block background
        capped = min(len(g.locations), _MAX_LOCS_COMPACT)
        overflow = len(g.locations) - capped
        loc_h = _loc_block_h(capped, overflow=overflow > 0)
        if loc_h > 0:
            self._rect(
                fitz.Rect(inner_left - 4, self.y - 9, card_right - 10, self.y - 9 + loc_h),
                fill=_C["loc_bg"],
                border=None,
                radius=0.02,
            )
        self._draw_locs_2col(g.locations, inner_left, max_n=_MAX_LOCS_COMPACT)

        self.y = card_top + card_h + 6

    # -- Table rows (LOW / STYLE) -------------------------------------------

    def _draw_table_header(self) -> None:
        row_h = 18
        self.ensure_space(row_h + 30)
        self._rect(
            fitz.Rect(_ML, self.y - 2, _PAGE_W - _MR, self.y - 2 + row_h),
            fill=_C["table_hdr_bg"],
            border=None,
        )
        hdr_y = self.y + 10
        self.page.insert_text(fitz.Point(_ML + 6, hdr_y), "SEV", fontsize=7, fontname=_FB, color=_C["text2"])
        self.page.insert_text(fitz.Point(_ML + 55, hdr_y), "FINDING", fontsize=7, fontname=_FB, color=_C["text2"])
        self.page.insert_text(fitz.Point(_PAGE_W - _MR - 30, hdr_y), "QTY", fontsize=7, fontname=_FB, color=_C["text2"])
        self.y += row_h + 1

    def draw_table_rows(self, groups: list[_GroupedFinding]) -> None:
        if not groups:
            return
        self._draw_table_header()

        for idx, g in enumerate(groups):
            sev_bg = _SEV_BG[g.severity]
            sev_fg = _SEV_FG[g.severity]

            # Truncate title if needed
            title_text = g.title
            max_title_w = _CW - 120
            if _tw(title_text, _FB, 8.5) > max_title_w:
                while _tw(title_text + "...", _FB, 8.5) > max_title_w and len(title_text) > 20:
                    title_text = title_text[:-1]
                title_text += "..."

            row_h = _measure_table_row(g)
            self.ensure_space(row_h + 2)

            # Alternating row background
            row_top = self.y - 2
            if idx % 2 == 0:
                self._rect(
                    fitz.Rect(_ML, row_top, _PAGE_W - _MR, row_top + row_h),
                    fill=_C["table_alt"],
                    border=None,
                )

            # Badge
            badge_y = self.y + 10
            self._badge(_ML + 4, badge_y, g.severity.name, bg=sev_bg, fg=sev_fg, size=6, hpad=3, vpad=1.5)

            # Title
            self.page.insert_text(
                fitz.Point(_ML + 55, self.y + 10),
                title_text,
                fontsize=8.5,
                fontname=_FB,
                color=_C["text"],
            )

            # Count
            self.page.insert_text(
                fitz.Point(_PAGE_W - _MR - 25, self.y + 10),
                str(g.count),
                fontsize=8.5,
                fontname=_FB,
                color=_C["text2"],
            )

            # Inline locations
            save_y = self.y
            self.y = save_y + 20
            self._draw_locs_inline(g.locations, _ML + 55, max_n=3)

            self.y = row_top + row_h + 1
            # Divider
            self.page.draw_line(
                fitz.Point(_ML, self.y - 2),
                fitz.Point(_PAGE_W - _MR, self.y - 2),
                color=_C["accent"],
                width=0.2,
            )

    # -- Finding dispatcher -------------------------------------------------

    def draw_grouped_findings(self, groups: list[_GroupedFinding]) -> None:
        full = [g for g in groups if g.severity in (Severity.CRITICAL, Severity.HIGH)]
        compact = [g for g in groups if g.severity == Severity.MEDIUM]
        table = [g for g in groups if g.severity in (Severity.LOW, Severity.STYLE)]

        for g in full:
            self.draw_full_card(g)
        for g in compact:
            self.draw_compact_card(g)
        if table:
            self.ensure_space(40)
            self.y += 4
            self._text(_ML, "Low & Style Issues", font=_FB, size=10, color=_C["text2"])
            self.y += 14
            self.draw_table_rows(table)

    # -- Summary table ------------------------------------------------------

    def draw_summary_table(self, findings: list[Finding]) -> None:
        self.ensure_space(200)
        self.register_section("Summary", level=1)

        self.y += 10
        self._text(_ML, "Report Summary", font=_FB, size=18, color=_C["white"])
        self.y += 8
        self.page.draw_line(
            fitz.Point(_ML, self.y),
            fitz.Point(_PAGE_W - _MR, self.y),
            color=_C["accent"],
            width=1.2,
        )
        self.y += 20

        # Build table data
        cat_counts: dict[str, dict[Severity, int]] = {}
        for f in findings:
            cat = _CHECK_TO_CATEGORY.get(f.check_name, f.check_name.title())
            cat_counts.setdefault(cat, {})
            cat_counts[cat][f.severity] = cat_counts[cat].get(f.severity, 0) + 1

        label_col_w = 130
        sev_col_w = 65
        total_col_w = 60
        table_w = label_col_w + len(Severity) * sev_col_w + total_col_w
        tl = _ML  # table left

        # Header row
        row_h = 22
        self._rect(
            fitz.Rect(tl, self.y - 2, tl + table_w, self.y - 2 + row_h),
            fill=_C["table_hdr_bg"],
            border=None,
        )
        hdr_y = self.y + 12
        self.page.insert_text(
            fitz.Point(tl + 8, hdr_y),
            "Category",
            fontsize=9,
            fontname=_FB,
            color=_C["text2"],
        )
        for i, sev in enumerate(Severity):
            self.page.insert_text(
                fitz.Point(tl + label_col_w + i * sev_col_w + 5, hdr_y),
                sev.name,
                fontsize=8,
                fontname=_FB,
                color=_C["text2"],
            )
        self.page.insert_text(
            fitz.Point(tl + label_col_w + len(Severity) * sev_col_w + 5, hdr_y),
            "TOTAL",
            fontsize=8,
            fontname=_FB,
            color=_C["text2"],
        )
        self.y += row_h + 2

        # Data rows
        row_idx = 0
        grand_total = 0
        grand_by_sev: dict[Severity, int] = {}
        for cat in _CATEGORY_ORDER:
            counts = cat_counts.get(cat)
            if not counts:
                continue
            row_total = sum(counts.values())
            grand_total += row_total
            for s, c in counts.items():
                grand_by_sev[s] = grand_by_sev.get(s, 0) + c

            row_top = self.y - 2
            if row_idx % 2 == 0:
                self._rect(
                    fitz.Rect(tl, row_top, tl + table_w, row_top + row_h),
                    fill=_C["table_alt"],
                    border=None,
                )
            data_y = self.y + 12
            self.page.insert_text(
                fitz.Point(tl + 8, data_y),
                cat,
                fontsize=9,
                fontname=_F,
                color=_C["text"],
            )
            for i, sev in enumerate(Severity):
                c = counts.get(sev, 0)
                if c > 0:
                    self.page.insert_text(
                        fitz.Point(tl + label_col_w + i * sev_col_w + 5, data_y),
                        str(c),
                        fontsize=9,
                        fontname=_F,
                        color=_SEV_BG[sev],
                    )
            self.page.insert_text(
                fitz.Point(tl + label_col_w + len(Severity) * sev_col_w + 5, data_y),
                str(row_total),
                fontsize=9,
                fontname=_FB,
                color=_C["white"],
            )
            self.y += row_h
            row_idx += 1

        # Grand total row
        self._rect(
            fitz.Rect(tl, self.y - 2, tl + table_w, self.y - 2 + row_h),
            fill=_C["card_bg"],
            border=_C["card_border"],
            width=0.5,
        )
        gt_y = self.y + 12
        self.page.insert_text(
            fitz.Point(tl + 8, gt_y),
            "TOTAL",
            fontsize=9,
            fontname=_FB,
            color=_C["white"],
        )
        for i, sev in enumerate(Severity):
            c = grand_by_sev.get(sev, 0)
            if c > 0:
                self.page.insert_text(
                    fitz.Point(tl + label_col_w + i * sev_col_w + 5, gt_y),
                    str(c),
                    fontsize=9,
                    fontname=_FB,
                    color=_SEV_BG[sev],
                )
        self.page.insert_text(
            fitz.Point(tl + label_col_w + len(Severity) * sev_col_w + 5, gt_y),
            str(grand_total),
            fontsize=9,
            fontname=_FB,
            color=_C["white"],
        )
        self.y += row_h + 20

        # Footer note
        self._text(
            _ML,
            f"Generated by Ren'Py Analyzer on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            font=_F,
            size=8,
            color=_C["text3"],
        )
        self._draw_footer()

    # -- Save ---------------------------------------------------------------

    def save(self, output_path: str) -> None:
        self._draw_footer()
        self.doc.save(output_path)
        self.doc.close()

        # Second pass: TOC page content, links, bookmarks
        self.doc = fitz.open(output_path)

        if hasattr(self, "_toc_page_idx") and self._toc_targets:
            toc_page = self.doc[self._toc_page_idx]
            y = self._toc_start_y
            for page_idx, target_y, title, level in self._toc_targets:
                page_display = page_idx + 1
                indent = 0 if level == 1 else 20

                # Entry title
                entry_font = _FB if level == 1 else _F
                entry_fs = 11 if level == 1 else 10
                toc_page.insert_text(
                    fitz.Point(_ML + indent, y),
                    title,
                    fontsize=entry_fs,
                    fontname=entry_font,
                    color=_C["white"],
                )
                # Page number
                pn_str = str(page_display)
                pn_w = _tw(pn_str, _F, 10)
                toc_page.insert_text(
                    fitz.Point(_PAGE_W - _MR - pn_w, y),
                    pn_str,
                    fontsize=10,
                    fontname=_F,
                    color=_C["text2"],
                )
                # Dotted leader
                title_w = _tw(title, entry_font, entry_fs)
                leader_start = _ML + indent + title_w + 8
                leader_end = _PAGE_W - _MR - pn_w - 8
                if leader_end > leader_start:
                    toc_page.draw_line(
                        fitz.Point(leader_start, y + 1),
                        fitz.Point(leader_end, y + 1),
                        color=_C["accent"],
                        width=0.5,
                        dashes="[2] 0",
                    )
                # Clickable link
                link_rect = fitz.Rect(_ML + indent, y - 12, _PAGE_W - _MR, y + 4)
                toc_page.insert_link(
                    {
                        "kind": fitz.LINK_GOTO,
                        "from": link_rect,
                        "page": page_idx,
                        "to": fitz.Point(0, max(0, target_y - 20)),
                    }
                )
                y += 22 if level == 1 else 18

        if self._bookmark_toc:
            self.doc.set_toc(self._bookmark_toc)

        self.doc.saveIncr()
        self.doc.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pdf(
    findings: list[Finding],
    output_path: str,
    game_name: str = "Ren'Py Project",
    game_path: str = "",
) -> None:
    """Generate a styled PDF report from analysis findings.

    Parameters
    ----------
    findings:
        List of Finding objects from the check modules.
    output_path:
        Destination file path for the PDF.
    game_name:
        Display name for the game / project (appears in title banner).
    game_path:
        Absolute path to the game root (used to show relative file paths).
    """
    builder = _PDFBuilder(game_name, game_path)

    # Title page
    builder.draw_title_page(findings)

    # Group findings
    grouped = _group_findings(findings, game_path)
    active_categories = [c for c in _CATEGORY_ORDER if c in grouped]

    # Table of contents
    builder.draw_toc_page(active_categories)

    # Finding sections
    for cat in active_categories:
        builder.new_page()
        cat_groups = grouped[cat]
        total_in_cat = sum(g.count for g in cat_groups)
        # Use the dominant severity colour for the section accent
        sev_color = _SEV_BG.get(cat_groups[0].severity) if cat_groups else None
        builder.draw_section_header(cat, total_in_cat, len(cat_groups), sev_color)
        builder.draw_grouped_findings(cat_groups)

    # Summary table
    builder.new_page()
    builder.draw_summary_table(findings)

    # Save
    builder.save(output_path)
