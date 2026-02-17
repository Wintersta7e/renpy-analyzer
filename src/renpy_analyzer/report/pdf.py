"""Styled PDF report generator using PyMuPDF.

Produces a professional A4 report with:
- Dark navy title banner with game name
- Summary section with color-coded severity counts
- Clickable table of contents
- Findings grouped by check category AND deduplicated by title
- Tiered display: full cards for CRITICAL/HIGH, compact for MEDIUM, table rows for LOW/STYLE
- Color-coded severity badges
- Summary table at the end
- PDF bookmark sidebar for navigation
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
# Colour palette
# ---------------------------------------------------------------------------

_COLOURS = {
    "bg": (0.941, 0.937, 0.957),        # #F0EFF4 light lavender/grey
    "navy": (0.106, 0.157, 0.220),       # #1B2838 dark navy
    "white": (1.0, 1.0, 1.0),
    "black": (0.0, 0.0, 0.0),
    "dark_text": (0.15, 0.15, 0.15),
    "mid_text": (0.35, 0.35, 0.35),
    "light_text": (0.55, 0.55, 0.55),
    "rule": (0.78, 0.78, 0.82),          # subtle divider
    "card_bg": (0.97, 0.97, 0.98),       # finding card background
    "card_border": (0.85, 0.85, 0.88),
    "loc_bg": (0.94, 0.94, 0.96),        # location block background
}

_SEVERITY_COLOURS = {
    Severity.CRITICAL: (0.863, 0.208, 0.271),   # #DC3545
    Severity.HIGH:     (0.992, 0.494, 0.078),   # #FD7E14
    Severity.MEDIUM:   (1.000, 0.757, 0.027),   # #FFC107
    Severity.LOW:      (0.157, 0.655, 0.271),   # #28A745
    Severity.STYLE:    (0.424, 0.459, 0.490),   # #6C757D
}

_SEVERITY_BADGE_TEXT = {
    Severity.CRITICAL: (1.0, 1.0, 1.0),
    Severity.HIGH:     (1.0, 1.0, 1.0),
    Severity.MEDIUM:   (0.15, 0.15, 0.15),
    Severity.LOW:      (1.0, 1.0, 1.0),
    Severity.STYLE:    (1.0, 1.0, 1.0),
}

_CATEGORY_ORDER = ["Labels", "Variables", "Logic", "Menus", "Assets", "Characters"]

_CHECK_TO_CATEGORY = {
    "labels": "Labels",
    "variables": "Variables",
    "logic": "Logic",
    "menus": "Menus",
    "assets": "Assets",
    "characters": "Characters",
}

# ---------------------------------------------------------------------------
# Layout constants (A4 = 595 x 842 pt)
# ---------------------------------------------------------------------------

_PAGE_W, _PAGE_H = 595, 842
_MARGIN_L = 50
_MARGIN_R = 50
_MARGIN_T = 55
_MARGIN_B = 50
_CONTENT_W = _PAGE_W - _MARGIN_L - _MARGIN_R  # 495

# Fonts  (Base-14)
_FONT_SANS = "helv"       # Helvetica
_FONT_SANS_BOLD = "hebo"  # Helvetica-Bold
_FONT_MONO = "cour"       # Courier

# Font objects for measuring
_font_helv = fitz.Font("helv")
_font_hebo = fitz.Font("hebo")
_font_cour = fitz.Font("cour")

_FONT_METRICS = {
    _FONT_SANS: _font_helv,
    _FONT_SANS_BOLD: _font_hebo,
    _FONT_MONO: _font_cour,
}

# Location display constants
_LOC_FONT_SIZE = 7.5
_LOC_LINE_H = 11
_LOC_COL_W = (_CONTENT_W - 28) / 2  # Two columns within a card


def _text_width(text: str, fontname: str, fontsize: float) -> float:
    """Return the rendered width of *text* in points."""
    return _FONT_METRICS[fontname].text_length(text, fontsize=fontsize)


def _wrap_text(text: str, max_width: float, fontname: str, fontsize: float) -> list[str]:
    """Word-wrap *text* to fit within *max_width* points.  Returns lines."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        if _text_width(trial, fontname, fontsize) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Grouped finding model
# ---------------------------------------------------------------------------

@dataclass
class _GroupedFinding:
    """A deduplicated finding: one title with all locations collected."""

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
    """Group findings by category then deduplicate by title within each category.

    Returns {category: [_GroupedFinding, ...]} sorted by severity then title.
    """
    # First pass: bucket by (category, title)
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

    # Sort locations within each group
    for g in buckets.values():
        g.locations.sort(key=lambda loc: (loc[0], loc[1]))

    # Organize by category
    by_cat: dict[str, list[_GroupedFinding]] = {}
    for (cat, _title), group in buckets.items():
        by_cat.setdefault(cat, []).append(group)

    # Sort within each category: severity first, then title
    for cat in by_cat:
        by_cat[cat].sort(key=lambda g: (g.severity, g.title))

    return by_cat


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
        self.page_num = 0  # 1-based after first new_page()
        self.y = _MARGIN_T
        self._footer_drawn = False

        # Bookkeeping for TOC links  [(page_0indexed, y, title, level)]
        self._toc_targets: list[tuple[int, float, str, int]] = []
        # TOC entries for bookmark sidebar  [[level, title, page_1indexed]]
        self._bookmark_toc: list[list] = []

    # -- page management ----------------------------------------------------

    def new_page(self) -> fitz.Page:
        """Append a new A4 page, paint the background, and reset cursor."""
        if self.page is not None and not self._footer_drawn:
            self._draw_footer()
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.page_num += 1
        self.y = _MARGIN_T
        self._footer_drawn = False
        self.page.draw_rect(
            fitz.Rect(0, 0, _PAGE_W, _PAGE_H),
            fill=_COLOURS["bg"],
            color=None,
        )
        return self.page

    def _available(self) -> float:
        """Vertical space remaining on the current page."""
        return _PAGE_H - _MARGIN_B - self.y

    def ensure_space(self, needed: float) -> None:
        """Start a new page if fewer than *needed* points remain."""
        if self._available() < needed:
            self.new_page()

    # -- footer -------------------------------------------------------------

    def _draw_footer(self) -> None:
        """Draw page number centred at the bottom of the current page."""
        if self.page is None or self._footer_drawn:
            return
        self._footer_drawn = True
        text = f"Page {self.page_num}"
        fs = 8
        tw = _text_width(text, _FONT_SANS, fs)
        x = (_PAGE_W - tw) / 2
        self.page.insert_text(
            fitz.Point(x, _PAGE_H - 25),
            text,
            fontsize=fs,
            fontname=_FONT_SANS,
            color=_COLOURS["light_text"],
        )

    # -- primitive drawing helpers ------------------------------------------

    def _draw_text(
        self,
        x: float,
        text: str,
        fontname: str = _FONT_SANS,
        fontsize: float = 10,
        color: tuple = _COLOURS["dark_text"],
    ) -> float:
        """Insert a single line of text at (x, self.y).  Returns the text width."""
        self.page.insert_text(
            fitz.Point(x, self.y),
            text,
            fontsize=fontsize,
            fontname=fontname,
            color=color,
        )
        return _text_width(text, fontname, fontsize)

    def _draw_rect(
        self,
        rect: fitz.Rect,
        fill: tuple | None = None,
        color: tuple | None = None,
        width: float = 0.5,
        radius: float | None = None,
    ) -> None:
        kwargs: dict = {"fill": fill, "color": color, "width": width}
        if radius is not None:
            kwargs["radius"] = radius
        self.page.draw_rect(rect, **kwargs)

    def _draw_badge(
        self,
        x: float,
        y: float,
        text: str,
        bg: tuple,
        fg: tuple,
        fontsize: float = 8,
        h_pad: float = 6,
        v_pad: float = 3,
    ) -> float:
        """Draw a rounded-corner badge.  Returns the badge width."""
        tw = _text_width(text, _FONT_SANS_BOLD, fontsize)
        badge_w = tw + h_pad * 2
        badge_h = fontsize + v_pad * 2
        rect = fitz.Rect(x, y - badge_h + v_pad, x + badge_w, y + v_pad)
        self._draw_rect(rect, fill=bg, color=None, radius=0.25)
        text_x = x + h_pad
        self.page.insert_text(
            fitz.Point(text_x, y),
            text,
            fontsize=fontsize,
            fontname=_FONT_SANS_BOLD,
            color=fg,
        )
        return badge_w

    # -- location rendering helpers -----------------------------------------

    def _format_location(self, file: str, line: int) -> str:
        """Format a single location as 'file:line'."""
        return f"{file}:{line}"

    def _locations_block_height(self, locations: list[tuple[str, int]], two_col: bool = True) -> float:
        """Calculate the height needed for a locations block."""
        n = len(locations)
        if n == 0:
            return 0
        if two_col:
            rows = math.ceil(n / 2)
        else:
            rows = n
        return rows * _LOC_LINE_H + 6  # 6pt padding

    def _draw_locations_2col(
        self,
        locations: list[tuple[str, int]],
        left_x: float,
        max_locs: int | None = None,
    ) -> None:
        """Draw locations in a 2-column monospace block starting at self.y.

        If *max_locs* is set, only that many are shown, plus an "and N more" note.
        """
        show_locs = locations if max_locs is None else locations[:max_locs]
        overflow = len(locations) - len(show_locs)

        col_w = _LOC_COL_W
        col1_x = left_x
        col2_x = left_x + col_w + 8

        for i, (file, line) in enumerate(show_locs):
            loc_str = self._format_location(file, line)
            # Truncate if too wide
            while _text_width(loc_str, _FONT_MONO, _LOC_FONT_SIZE) > col_w - 4 and len(loc_str) > 20:
                loc_str = loc_str[:len(loc_str) - 4] + "..."
            x = col1_x if i % 2 == 0 else col2_x
            if i % 2 == 0 or i == 0:
                pass  # y is already set for this row
            self.page.insert_text(
                fitz.Point(x, self.y),
                loc_str,
                fontsize=_LOC_FONT_SIZE,
                fontname=_FONT_MONO,
                color=_COLOURS["mid_text"],
            )
            if i % 2 == 1 or i == len(show_locs) - 1:
                self.y += _LOC_LINE_H

        if overflow > 0:
            more_text = f"... and {overflow} more location{'s' if overflow != 1 else ''}"
            self.page.insert_text(
                fitz.Point(col1_x, self.y),
                more_text,
                fontsize=_LOC_FONT_SIZE,
                fontname=_FONT_SANS,
                color=_COLOURS["light_text"],
            )
            self.y += _LOC_LINE_H

    def _draw_locations_inline(
        self,
        locations: list[tuple[str, int]],
        left_x: float,
        max_locs: int = 3,
    ) -> None:
        """Draw locations inline on a single line (for compact table rows)."""
        show = locations[:max_locs]
        overflow = len(locations) - len(show)
        parts = [self._format_location(f, ln) for f, ln in show]
        if overflow > 0:
            parts.append(f"and {overflow} more")
        text = "  |  ".join(parts)
        # Truncate if needed
        max_w = _CONTENT_W - (left_x - _MARGIN_L) - 10
        while _text_width(text, _FONT_MONO, 7) > max_w and len(text) > 30:
            text = text[:len(text) - 4] + "..."
        self.page.insert_text(
            fitz.Point(left_x, self.y),
            text,
            fontsize=7,
            fontname=_FONT_MONO,
            color=_COLOURS["light_text"],
        )

    # -- high-level sections ------------------------------------------------

    def draw_title_page(self, findings: list[Finding]) -> None:
        """Render the title / cover page."""
        self.new_page()

        # -- Navy banner (full width, top) --
        banner_h = 100
        self._draw_rect(
            fitz.Rect(0, 0, _PAGE_W, banner_h),
            fill=_COLOURS["navy"],
            color=None,
        )

        # Title text
        self.y = 48
        self._draw_text(
            _MARGIN_L, self.game_name,
            fontname=_FONT_SANS_BOLD, fontsize=24, color=_COLOURS["white"],
        )
        # Subtitle
        self.y = 72
        self._draw_text(
            _MARGIN_L, "Ren'Py Analyzer Report",
            fontname=_FONT_SANS, fontsize=12, color=(0.7, 0.75, 0.82),
        )
        # Date
        self.y = 90
        date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
        self._draw_text(
            _MARGIN_L, date_str,
            fontname=_FONT_SANS, fontsize=9, color=(0.55, 0.6, 0.68),
        )

        # -- Project path (below banner) --
        self.y = banner_h + 22
        if self.game_path:
            self._draw_text(
                _MARGIN_L, "Project path:",
                fontname=_FONT_SANS_BOLD, fontsize=9, color=_COLOURS["mid_text"],
            )
            self.y += 13
            display_path = self.game_path
            max_path_w = _CONTENT_W
            while _text_width(display_path, _FONT_MONO, 8) > max_path_w and len(display_path) > 40:
                display_path = "..." + display_path[4:]
            self._draw_text(
                _MARGIN_L, display_path,
                fontname=_FONT_MONO, fontsize=8, color=_COLOURS["mid_text"],
            )
            self.y += 20

        # -- Summary statistics --
        self.y += 5
        self._draw_text(
            _MARGIN_L, "Summary",
            fontname=_FONT_SANS_BOLD, fontsize=18, color=_COLOURS["dark_text"],
        )
        self.y += 6
        self.page.draw_line(
            fitz.Point(_MARGIN_L, self.y),
            fitz.Point(_PAGE_W - _MARGIN_R, self.y),
            color=_COLOURS["rule"], width=0.8,
        )
        self.y += 18

        # Severity counts
        severity_counts = Counter(f.severity for f in findings)
        total = len(findings)

        # Total findings - big number
        self._draw_text(
            _MARGIN_L, str(total),
            fontname=_FONT_SANS_BOLD, fontsize=40, color=_COLOURS["navy"],
        )
        total_w = _text_width(str(total), _FONT_SANS_BOLD, 40)
        save_y = self.y
        self.y -= 11
        self._draw_text(
            _MARGIN_L + total_w + 10, "Total Findings",
            fontname=_FONT_SANS, fontsize=14, color=_COLOURS["mid_text"],
        )
        self.y = save_y + 25

        # Severity badges row
        x = _MARGIN_L
        for sev in Severity:
            count = severity_counts.get(sev, 0)
            label = f"{sev.name}  {count}"
            badge_w = self._draw_badge(
                x, self.y, label,
                bg=_SEVERITY_COLOURS[sev],
                fg=_SEVERITY_BADGE_TEXT[sev],
                fontsize=10,
                h_pad=10,
                v_pad=5,
            )
            x += badge_w + 12
        self.y += 28

        # -- Category breakdown table --
        self.y += 10
        self._draw_text(
            _MARGIN_L, "Findings by Category",
            fontname=_FONT_SANS_BOLD, fontsize=14, color=_COLOURS["dark_text"],
        )
        self.y += 18

        cat_counts: dict[str, Counter] = {}
        for f in findings:
            cat = _CHECK_TO_CATEGORY.get(f.check_name, f.check_name.title())
            cat_counts.setdefault(cat, Counter())[f.severity] += 1

        # Table header
        col_x = [_MARGIN_L, _MARGIN_L + 130]
        sev_col_w = 65
        for i, _sev in enumerate(Severity):
            col_x.append(_MARGIN_L + 130 + i * sev_col_w)
        col_x.append(_MARGIN_L + 130 + len(Severity) * sev_col_w)

        header_y = self.y
        self._draw_rect(
            fitz.Rect(_MARGIN_L, header_y - 12, _PAGE_W - _MARGIN_R, header_y + 4),
            fill=_COLOURS["navy"], color=None,
        )
        self._draw_text(
            col_x[0] + 5, "Category",
            fontname=_FONT_SANS_BOLD, fontsize=9, color=_COLOURS["white"],
        )
        for i, sev in enumerate(Severity):
            self._draw_text(
                col_x[1] + i * sev_col_w + 5, sev.name,
                fontname=_FONT_SANS_BOLD, fontsize=8, color=_COLOURS["white"],
            )
        self._draw_text(
            col_x[-1] + 5, "TOTAL",
            fontname=_FONT_SANS_BOLD, fontsize=8, color=_COLOURS["white"],
        )
        self.y += 16

        # Table rows
        for cat in _CATEGORY_ORDER:
            counts = cat_counts.get(cat, Counter())
            row_total = sum(counts.values())
            if row_total == 0:
                continue
            self._draw_text(
                col_x[0] + 5, cat,
                fontname=_FONT_SANS, fontsize=9, color=_COLOURS["dark_text"],
            )
            for i, sev in enumerate(Severity):
                c = counts.get(sev, 0)
                if c > 0:
                    self._draw_text(
                        col_x[1] + i * sev_col_w + 5, str(c),
                        fontname=_FONT_SANS, fontsize=9, color=_SEVERITY_COLOURS[sev],
                    )
            self._draw_text(
                col_x[-1] + 5, str(row_total),
                fontname=_FONT_SANS_BOLD, fontsize=9, color=_COLOURS["dark_text"],
            )
            self.y += 16
            self.page.draw_line(
                fitz.Point(_MARGIN_L, self.y - 8),
                fitz.Point(_PAGE_W - _MARGIN_R, self.y - 8),
                color=_COLOURS["rule"], width=0.3,
            )

        # -- Unique findings count --
        self.y += 16
        unique_titles = len({f.title for f in findings})
        note = (
            f"{total} total findings condensed into {unique_titles} unique issues in this report."
        )
        self._draw_text(
            _MARGIN_L, note,
            fontname=_FONT_SANS, fontsize=9, color=_COLOURS["mid_text"],
        )

        self._draw_footer()

    def draw_toc_page(self, categories: list[str]) -> int:
        """Draw a table of contents page.  Returns the 0-indexed page number."""
        self.new_page()
        toc_page_idx = self.page_num - 1

        self.y = _MARGIN_T + 5
        self._draw_text(
            _MARGIN_L, "Table of Contents",
            fontname=_FONT_SANS_BOLD, fontsize=20, color=_COLOURS["navy"],
        )
        self.y += 8
        self.page.draw_line(
            fitz.Point(_MARGIN_L, self.y),
            fitz.Point(_PAGE_W - _MARGIN_R, self.y),
            color=_COLOURS["navy"], width=1.2,
        )
        self.y += 25

        self._toc_start_y = self.y
        self._toc_page_idx = toc_page_idx

        self._draw_footer()
        return toc_page_idx

    def register_section(self, title: str, level: int = 1) -> None:
        """Record the current position as a TOC / bookmark target."""
        page_idx = self.page_num - 1
        self._toc_targets.append((page_idx, self.y, title, level))
        self._bookmark_toc.append([level, title, self.page_num])

    def draw_section_header(self, title: str, finding_count: int, group_count: int) -> None:
        """Draw a category section header with both total findings and unique groups."""
        self.ensure_space(60)
        self.register_section(title, level=1)

        # Accent bar
        bar_h = 32
        self._draw_rect(
            fitz.Rect(_MARGIN_L, self.y - 4, _MARGIN_L + 5, self.y - 4 + bar_h),
            fill=_COLOURS["navy"], color=None,
        )
        # Title
        self._draw_text(
            _MARGIN_L + 14, title,
            fontname=_FONT_SANS_BOLD, fontsize=16, color=_COLOURS["navy"],
        )
        # Count badge
        if finding_count == group_count:
            count_text = f"{finding_count} finding{'s' if finding_count != 1 else ''}"
        else:
            count_text = f"{finding_count} findings in {group_count} unique issues"
        tw = _text_width(title, _FONT_SANS_BOLD, 16)
        self._draw_badge(
            _MARGIN_L + 14 + tw + 12, self.y,
            count_text,
            bg=(0.88, 0.88, 0.92),
            fg=_COLOURS["mid_text"],
            fontsize=8,
        )
        self.y += bar_h + 8

    # -- Tiered finding renderers -------------------------------------------

    def _estimate_full_card_height(self, group: _GroupedFinding) -> float:
        """Estimate height for a CRITICAL/HIGH full card."""
        title_lines = _wrap_text(group.title, _CONTENT_W - 100, _FONT_SANS_BOLD, 11)
        desc_lines = _wrap_text(group.description, _CONTENT_W - 28, _FONT_SANS, 9)
        sugg_lines = (
            _wrap_text(group.suggestion, _CONTENT_W - 36, _FONT_SANS, 9)
            if group.suggestion else []
        )
        loc_h = self._locations_block_height(group.locations, two_col=True)

        h = (
            16                              # top padding + badge line
            + len(title_lines) * 14         # title
            + 8                             # gap after title
            + len(desc_lines) * 12          # description
            + (8 + len(sugg_lines) * 12 if sugg_lines else 0)
            + 10                            # gap before locations
            + loc_h                         # location block
            + 10                            # bottom padding
        )
        return max(h, 60)

    def draw_full_card(self, group: _GroupedFinding) -> None:
        """Draw a full finding card for CRITICAL/HIGH severity (grouped)."""
        sev = group.severity
        sev_color = _SEVERITY_COLOURS[sev]
        sev_text_color = _SEVERITY_BADGE_TEXT[sev]

        card_h = self._estimate_full_card_height(group)
        self.ensure_space(card_h + 8)

        card_top = self.y - 4
        card_left = _MARGIN_L
        card_right = _PAGE_W - _MARGIN_R

        # Card background with left accent
        self._draw_rect(
            fitz.Rect(card_left, card_top, card_right, card_top + card_h),
            fill=_COLOURS["card_bg"],
            color=_COLOURS["card_border"],
            width=0.4,
            radius=0.02,
        )
        # Left colour accent
        self._draw_rect(
            fitz.Rect(card_left, card_top, card_left + 4, card_top + card_h),
            fill=sev_color,
            color=None,
        )

        inner_left = card_left + 14
        self.y = card_top + 16

        # Severity badge
        badge_w = self._draw_badge(
            inner_left, self.y, sev.name,
            bg=sev_color, fg=sev_text_color,
            fontsize=7, h_pad=5, v_pad=2,
        )

        # Occurrence count
        if group.count > 1:
            count_label = f"{group.count} occurrences"
            self._draw_badge(
                inner_left + badge_w + 8, self.y, count_label,
                bg=(0.88, 0.88, 0.92), fg=_COLOURS["mid_text"],
                fontsize=7, h_pad=4, v_pad=2,
            )
        self.y += 14

        # Title (wrapped)
        title_lines = _wrap_text(group.title, _CONTENT_W - 100, _FONT_SANS_BOLD, 11)
        for tl in title_lines:
            self._draw_text(
                inner_left, tl,
                fontname=_FONT_SANS_BOLD, fontsize=11, color=_COLOURS["dark_text"],
            )
            self.y += 14

        self.y += 2

        # Description (wrapped)
        desc_lines = _wrap_text(group.description, _CONTENT_W - 28, _FONT_SANS, 9)
        for dl in desc_lines:
            self._draw_text(
                inner_left, dl,
                fontname=_FONT_SANS, fontsize=9, color=_COLOURS["dark_text"],
            )
            self.y += 12

        # Suggestion
        if group.suggestion:
            sugg_lines = _wrap_text(group.suggestion, _CONTENT_W - 36, _FONT_SANS, 9)
            self.y += 4
            self._draw_text(
                inner_left, "Suggestion:",
                fontname=_FONT_SANS_BOLD, fontsize=8, color=(0.25, 0.50, 0.35),
            )
            self.y += 12
            for sl in sugg_lines:
                self._draw_text(
                    inner_left + 8, sl,
                    fontname=_FONT_SANS, fontsize=9, color=(0.30, 0.45, 0.35),
                )
                self.y += 12

        # Locations header
        self.y += 4
        self._draw_text(
            inner_left, "Locations:",
            fontname=_FONT_SANS_BOLD, fontsize=8, color=_COLOURS["mid_text"],
        )
        self.y += 11

        # Location block (2-column, all locations)
        self._draw_locations_2col(group.locations, inner_left)

        # Finalize card: adjust if we went past estimated height
        actual_bottom = self.y + 6
        final_bottom = max(card_top + card_h, actual_bottom)
        if final_bottom > card_top + card_h:
            # Redraw card background to cover actual content
            self._draw_rect(
                fitz.Rect(card_left, card_top, card_right, final_bottom),
                fill=None,
                color=_COLOURS["card_border"],
                width=0.4,
                radius=0.02,
            )
        self.y = final_bottom + 8

    def _estimate_compact_card_height(self, group: _GroupedFinding) -> float:
        """Estimate height for a MEDIUM compact card."""
        title_lines = _wrap_text(group.title, _CONTENT_W - 100, _FONT_SANS_BOLD, 10)
        # Single-line description (truncated)
        desc_lines = _wrap_text(group.description, _CONTENT_W - 28, _FONT_SANS, 8.5)
        desc_line_count = min(len(desc_lines), 2)  # Max 2 lines for description

        loc_h = self._locations_block_height(group.locations, two_col=True)

        h = (
            14                              # top padding + badge
            + len(title_lines) * 13         # title
            + 4                             # gap
            + desc_line_count * 11          # description (max 2 lines)
            + 8                             # gap before locations
            + loc_h                         # locations
            + 8                             # bottom padding
        )
        return max(h, 44)

    def draw_compact_card(self, group: _GroupedFinding) -> None:
        """Draw a compact finding card for MEDIUM severity (grouped)."""
        sev = group.severity
        sev_color = _SEVERITY_COLOURS[sev]
        sev_text_color = _SEVERITY_BADGE_TEXT[sev]

        card_h = self._estimate_compact_card_height(group)
        self.ensure_space(card_h + 6)

        card_top = self.y - 2
        card_left = _MARGIN_L
        card_right = _PAGE_W - _MARGIN_R

        # Card background
        self._draw_rect(
            fitz.Rect(card_left, card_top, card_right, card_top + card_h),
            fill=_COLOURS["card_bg"],
            color=_COLOURS["card_border"],
            width=0.3,
            radius=0.02,
        )
        # Left accent (thin)
        self._draw_rect(
            fitz.Rect(card_left, card_top, card_left + 3, card_top + card_h),
            fill=sev_color,
            color=None,
        )

        inner_left = card_left + 12
        self.y = card_top + 13

        # Badge + count on same line
        badge_w = self._draw_badge(
            inner_left, self.y, sev.name,
            bg=sev_color, fg=sev_text_color,
            fontsize=6.5, h_pad=4, v_pad=2,
        )
        if group.count > 1:
            count_label = f"x{group.count}"
            self._draw_badge(
                inner_left + badge_w + 6, self.y, count_label,
                bg=(0.88, 0.88, 0.92), fg=_COLOURS["mid_text"],
                fontsize=6.5, h_pad=3, v_pad=2,
            )
        self.y += 12

        # Title
        title_lines = _wrap_text(group.title, _CONTENT_W - 100, _FONT_SANS_BOLD, 10)
        for tl in title_lines:
            self._draw_text(
                inner_left, tl,
                fontname=_FONT_SANS_BOLD, fontsize=10, color=_COLOURS["dark_text"],
            )
            self.y += 13
        self.y += 2

        # Description (max 2 lines)
        desc_lines = _wrap_text(group.description, _CONTENT_W - 28, _FONT_SANS, 8.5)
        for dl in desc_lines[:2]:
            self._draw_text(
                inner_left, dl,
                fontname=_FONT_SANS, fontsize=8.5, color=_COLOURS["mid_text"],
            )
            self.y += 11

        # Locations (2-column)
        self.y += 3
        self._draw_locations_2col(group.locations, inner_left)

        actual_bottom = self.y + 4
        final_bottom = max(card_top + card_h, actual_bottom)
        if final_bottom > card_top + card_h:
            self._draw_rect(
                fitz.Rect(card_left, card_top, card_right, final_bottom),
                fill=None,
                color=_COLOURS["card_border"],
                width=0.3,
                radius=0.02,
            )
        self.y = final_bottom + 6

    def _draw_table_header_row(self) -> None:
        """Draw the header row for the LOW/STYLE compact table."""
        row_h = 18
        self.ensure_space(row_h + 30)  # header + at least one data row

        self._draw_rect(
            fitz.Rect(_MARGIN_L, self.y - 2, _PAGE_W - _MARGIN_R, self.y - 2 + row_h),
            fill=_COLOURS["navy"], color=None,
        )
        hdr_y = self.y + 10
        self.page.insert_text(
            fitz.Point(_MARGIN_L + 6, hdr_y), "SEV",
            fontsize=7, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
        )
        self.page.insert_text(
            fitz.Point(_MARGIN_L + 55, hdr_y), "FINDING",
            fontsize=7, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
        )
        self.page.insert_text(
            fitz.Point(_PAGE_W - _MARGIN_R - 30, hdr_y), "QTY",
            fontsize=7, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
        )
        self.y += row_h + 1

    def draw_table_rows(self, groups: list[_GroupedFinding]) -> None:
        """Draw LOW/STYLE findings as compact table rows with locations."""
        if not groups:
            return

        self._draw_table_header_row()

        for idx, group in enumerate(groups):
            sev = group.severity
            sev_color = _SEVERITY_COLOURS[sev]
            sev_text_color = _SEVERITY_BADGE_TEXT[sev]

            # Calculate row height: title line + locations line
            title_text = group.title
            max_title_w = _CONTENT_W - 120
            if _text_width(title_text, _FONT_SANS_BOLD, 8.5) > max_title_w:
                while (
                    _text_width(title_text + "...", _FONT_SANS_BOLD, 8.5) > max_title_w
                    and len(title_text) > 20
                ):
                    title_text = title_text[:-1]
                title_text += "..."

            row_h = 28  # title line + location line + padding
            self.ensure_space(row_h + 2)

            # Alternating row background
            row_top = self.y - 2
            if idx % 2 == 0:
                self._draw_rect(
                    fitz.Rect(_MARGIN_L, row_top, _PAGE_W - _MARGIN_R, row_top + row_h),
                    fill=(0.96, 0.96, 0.97), color=None,
                )

            # Severity badge (small)
            badge_y = self.y + 10
            self._draw_badge(
                _MARGIN_L + 4, badge_y, sev.name,
                bg=sev_color, fg=sev_text_color,
                fontsize=6, h_pad=3, v_pad=1.5,
            )

            # Title
            self.page.insert_text(
                fitz.Point(_MARGIN_L + 55, self.y + 10),
                title_text,
                fontsize=8.5,
                fontname=_FONT_SANS_BOLD,
                color=_COLOURS["dark_text"],
            )

            # Count
            self.page.insert_text(
                fitz.Point(_PAGE_W - _MARGIN_R - 25, self.y + 10),
                str(group.count),
                fontsize=8.5,
                fontname=_FONT_SANS_BOLD,
                color=_COLOURS["mid_text"],
            )

            # Locations (inline, under the title)
            save_y = self.y
            self.y = save_y + 20
            self._draw_locations_inline(group.locations, _MARGIN_L + 55, max_locs=3)

            self.y = row_top + row_h + 1

            # Thin divider
            self.page.draw_line(
                fitz.Point(_MARGIN_L, self.y - 2),
                fitz.Point(_PAGE_W - _MARGIN_R, self.y - 2),
                color=_COLOURS["rule"], width=0.2,
            )

    # -- finding dispatcher -------------------------------------------------

    def draw_grouped_findings(self, groups: list[_GroupedFinding]) -> None:
        """Render a list of grouped findings using tiered display.

        - CRITICAL/HIGH  -> full card
        - MEDIUM         -> compact card
        - LOW/STYLE      -> collected into a table
        """
        full_groups = [g for g in groups if g.severity in (Severity.CRITICAL, Severity.HIGH)]
        compact_groups = [g for g in groups if g.severity == Severity.MEDIUM]
        table_groups = [g for g in groups if g.severity in (Severity.LOW, Severity.STYLE)]

        # Full cards
        for g in full_groups:
            self.draw_full_card(g)

        # Compact cards
        for g in compact_groups:
            self.draw_compact_card(g)

        # Table rows
        if table_groups:
            self.ensure_space(40)
            # Sub-header for the table section
            self.y += 4
            self._draw_text(
                _MARGIN_L, "Low & Style Issues",
                fontname=_FONT_SANS_BOLD, fontsize=10, color=_COLOURS["mid_text"],
            )
            self.y += 14
            self.draw_table_rows(table_groups)

    # -- summary table (end of report) --------------------------------------

    def draw_summary_table(self, findings: list[Finding]) -> None:
        """Draw a final summary table at the end of the report."""
        self.ensure_space(200)
        self.register_section("Summary", level=1)

        self.y += 10
        self._draw_text(
            _MARGIN_L, "Report Summary",
            fontname=_FONT_SANS_BOLD, fontsize=18, color=_COLOURS["navy"],
        )
        self.y += 8
        self.page.draw_line(
            fitz.Point(_MARGIN_L, self.y),
            fitz.Point(_PAGE_W - _MARGIN_R, self.y),
            color=_COLOURS["navy"], width=1.2,
        )
        self.y += 20

        # Build table data
        cat_counts: dict[str, dict[Severity, int]] = {}
        for f in findings:
            cat = _CHECK_TO_CATEGORY.get(f.check_name, f.check_name.title())
            cat_counts.setdefault(cat, {})
            cat_counts[cat][f.severity] = cat_counts[cat].get(f.severity, 0) + 1

        col_label_w = 130
        sev_col_w = 65
        total_col_w = 60
        table_w = col_label_w + len(Severity) * sev_col_w + total_col_w
        table_left = _MARGIN_L

        # Header row
        row_h = 22
        self._draw_rect(
            fitz.Rect(table_left, self.y - 2, table_left + table_w, self.y - 2 + row_h),
            fill=_COLOURS["navy"], color=None,
        )
        hdr_y = self.y + 12
        self.page.insert_text(
            fitz.Point(table_left + 8, hdr_y), "Category",
            fontsize=9, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
        )
        for i, sev in enumerate(Severity):
            self.page.insert_text(
                fitz.Point(table_left + col_label_w + i * sev_col_w + 5, hdr_y),
                sev.name, fontsize=8, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
            )
        self.page.insert_text(
            fitz.Point(table_left + col_label_w + len(Severity) * sev_col_w + 5, hdr_y),
            "TOTAL", fontsize=8, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
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
                self._draw_rect(
                    fitz.Rect(table_left, row_top, table_left + table_w, row_top + row_h),
                    fill=(0.96, 0.96, 0.97), color=None,
                )
            data_y = self.y + 12
            self.page.insert_text(
                fitz.Point(table_left + 8, data_y), cat,
                fontsize=9, fontname=_FONT_SANS, color=_COLOURS["dark_text"],
            )
            for i, sev in enumerate(Severity):
                c = counts.get(sev, 0)
                if c > 0:
                    self.page.insert_text(
                        fitz.Point(table_left + col_label_w + i * sev_col_w + 5, data_y),
                        str(c), fontsize=9, fontname=_FONT_SANS, color=_SEVERITY_COLOURS[sev],
                    )
            self.page.insert_text(
                fitz.Point(table_left + col_label_w + len(Severity) * sev_col_w + 5, data_y),
                str(row_total), fontsize=9, fontname=_FONT_SANS_BOLD, color=_COLOURS["dark_text"],
            )
            self.y += row_h
            row_idx += 1

        # Grand total row
        self._draw_rect(
            fitz.Rect(table_left, self.y - 2, table_left + table_w, self.y - 2 + row_h),
            fill=_COLOURS["navy"], color=None,
        )
        gt_y = self.y + 12
        self.page.insert_text(
            fitz.Point(table_left + 8, gt_y), "TOTAL",
            fontsize=9, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
        )
        for i, sev in enumerate(Severity):
            c = grand_by_sev.get(sev, 0)
            if c > 0:
                self.page.insert_text(
                    fitz.Point(table_left + col_label_w + i * sev_col_w + 5, gt_y),
                    str(c), fontsize=9, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
                )
        self.page.insert_text(
            fitz.Point(table_left + col_label_w + len(Severity) * sev_col_w + 5, gt_y),
            str(grand_total), fontsize=9, fontname=_FONT_SANS_BOLD, color=_COLOURS["white"],
        )
        self.y += row_h + 20

        # Footer note
        self._draw_text(
            _MARGIN_L,
            f"Generated by Ren'Py Analyzer on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            fontname=_FONT_SANS, fontsize=8, color=_COLOURS["light_text"],
        )

        self._draw_footer()

    # -- finalize -----------------------------------------------------------

    def save(self, output_path: str) -> None:
        """Write the PDF to disk, inserting TOC links and bookmarks."""
        self._draw_footer()

        self.doc.save(output_path)
        self.doc.close()

        # Second pass: reopen and add TOC page content, links, bookmarks
        self.doc = fitz.open(output_path)

        if hasattr(self, "_toc_page_idx") and self._toc_targets:
            toc_page = self.doc[self._toc_page_idx]
            y = self._toc_start_y
            for page_idx, target_y, title, level in self._toc_targets:
                page_display = page_idx + 1
                indent = 0 if level == 1 else 20

                toc_page.insert_text(
                    fitz.Point(_MARGIN_L + indent, y),
                    title,
                    fontsize=11 if level == 1 else 10,
                    fontname=_FONT_SANS_BOLD if level == 1 else _FONT_SANS,
                    color=_COLOURS["navy"],
                )
                page_str = str(page_display)
                pn_w = _text_width(page_str, _FONT_SANS, 10)
                toc_page.insert_text(
                    fitz.Point(_PAGE_W - _MARGIN_R - pn_w, y),
                    page_str,
                    fontsize=10,
                    fontname=_FONT_SANS,
                    color=_COLOURS["mid_text"],
                )
                # Dotted leader line
                title_font = _FONT_SANS_BOLD if level == 1 else _FONT_SANS
                title_fs = 11 if level == 1 else 10
                leader_start = _MARGIN_L + indent + _text_width(title, title_font, title_fs) + 8
                leader_end = _PAGE_W - _MARGIN_R - pn_w - 8
                if leader_end > leader_start:
                    toc_page.draw_line(
                        fitz.Point(leader_start, y + 1),
                        fitz.Point(leader_end, y + 1),
                        color=_COLOURS["rule"],
                        width=0.5,
                        dashes="[2] 0",
                    )

                link_rect = fitz.Rect(_MARGIN_L + indent, y - 12, _PAGE_W - _MARGIN_R, y + 4)
                lnk = {
                    "kind": fitz.LINK_GOTO,
                    "from": link_rect,
                    "page": page_idx,
                    "to": fitz.Point(0, max(0, target_y - 20)),
                }
                toc_page.insert_link(lnk)

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

    # -- Title page --
    builder.draw_title_page(findings)

    # -- Group findings by category and deduplicate by title --
    grouped = _group_findings(findings, game_path)

    # Determine which categories have findings
    active_categories = [c for c in _CATEGORY_ORDER if c in grouped]

    # -- Table of contents --
    builder.draw_toc_page(active_categories)

    # -- Finding sections --
    for cat in active_categories:
        builder.new_page()
        cat_groups = grouped[cat]
        total_findings_in_cat = sum(g.count for g in cat_groups)
        builder.draw_section_header(cat, total_findings_in_cat, len(cat_groups))
        builder.draw_grouped_findings(cat_groups)

    # -- Summary table --
    builder.new_page()
    builder.draw_summary_table(findings)

    # -- Save --
    builder.save(output_path)
