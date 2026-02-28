"""Ren'Py Analyzer GUI -- Midnight theme, VS Error List Treeview, persistent settings."""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, ttk

import customtkinter as ctk

from . import __version__
from .analyzer import run_analysis
from .checks import ALL_CHECKS
from .log import setup_logging
from .models import Finding, Severity
from .report.pdf import generate_pdf
from .sdk_bridge import detect_sdk_version, validate_sdk_path
from .settings import Settings
from .version import detect_renpy_version, format_version, select_sdk

logger = logging.getLogger("renpy_analyzer.app")

# ---------------------------------------------------------------------------
# Midnight palette
# ---------------------------------------------------------------------------

MIDNIGHT_BG = "#0D1B2A"
PANEL_BG = "#1B2838"
PANEL_LIGHTER = "#243447"
PANEL_BORDER = "#2D4A5E"
TEXT_PRIMARY = "#E0E6ED"
TEXT_DIM = "#7A8B9A"
ACCENT_BLUE = "#1F6FEB"

SEVERITY_COLORS: dict[Severity, str] = {
    Severity.CRITICAL: "#DC3545",
    Severity.HIGH: "#FD7E14",
    Severity.MEDIUM: "#FFC107",
    Severity.LOW: "#28A745",
    Severity.STYLE: "#6C757D",
}

# Friendly labels for check names in the checkbox grid
_CHECK_LABELS: dict[str, str] = {
    "Labels": "Labels & Jumps",
    "Variables": "Variables",
    "Logic": "Logic Errors",
    "Menus": "Menus",
    "Assets": "Assets",
    "Characters": "Characters",
    "Flow": "Unreachable Code",
    "Screens": "Screens",
    "Transforms": "Transforms",
    "Translations": "Translations",
    "Text Tags": "Text Tags",
    "Call Safety": "Call Safety",
    "Call Cycles": "Call Cycles",
    "Empty Labels": "Empty Labels",
    "Persistent Vars": "Persistent Vars",
}

# Treeview column definitions: (id, heading, width, stretch, anchor)
_TREE_COLUMNS = [
    ("severity", "Severity", 100, False, "center"),
    ("check", "Check", 140, False, "w"),
    ("description", "Description", 420, True, "w"),
    ("file", "File", 240, True, "w"),
    ("line", "Line", 65, False, "center"),
]

# Sentinel for the "no SDK" option in the dropdown
_NO_SDK_LABEL = "None (regex parser)"


class RenpyAnalyzerApp(ctk.CTk):
    """Main application window for Ren'Py Analyzer — midnight theme."""

    def __init__(self) -> None:
        super().__init__()

        # Load persistent settings
        self._settings = Settings.load()

        self.title(f"Ren'Py Analyzer v{__version__}")
        self.geometry(self._settings.window_geometry)
        self.minsize(820, 600)
        self.configure(fg_color=MIDNIGHT_BG)

        # State
        self._path_var = StringVar(value=self._settings.game_path)
        self._sdk_note = StringVar(value="")
        self._game_dir_note = StringVar(value="")
        self._check_vars: dict[str, BooleanVar] = {}
        self._findings: list[Finding] = []
        self._filtered_findings: list[Finding] = []
        self._project_path: str = ""
        self._analysis_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._severity_counts: dict[Severity, int] = {}
        self._severity_active: dict[Severity, bool] = {}
        self._severity_buttons: dict[Severity, ctk.CTkButton] = {}
        self._sort_column = self._settings.sort_column
        self._sort_ascending = self._settings.sort_ascending

        # SDK manager state: list of (path, version_str) tuples
        self._sdk_entries: list[tuple[str, str]] = []
        self._sdk_dropdown_var = StringVar(value=_NO_SDK_LABEL)
        self._resolved_sdk_path: str | None = None
        self._load_sdk_entries()

        # Initialize severity filters from settings
        for sev in Severity:
            saved = self._settings.severity_filters.get(sev.name, True)
            self._severity_active[sev] = saved

        # Configure ttk style BEFORE building widgets (global — uses 'default' theme
        # because OS themes ignore custom color settings on Treeview)
        self._configure_treeview_style()

        # Grid layout: 7 rows, row 4 expands
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._build_header()       # Row 0
        self._build_input_panel()  # Row 1
        self._build_checks_panel() # Row 2
        self._build_action_bar()   # Row 3
        self._build_results()      # Row 4
        self._build_detail_panel() # Row 5
        self._build_status_bar()   # Row 6

        # Configure tag colors on the Treeview (after it's built)
        self._configure_treeview_tags()

        # Restore game dir note if path was loaded from settings
        if self._path_var.get():
            game_sub = Path(self._path_var.get()) / "game"
            if game_sub.is_dir():
                self._game_dir_note.set("game/ subfolder detected — will scan automatically.")
            self._update_sdk_auto_note()

    # -----------------------------------------------------------------------
    # SDK management
    # -----------------------------------------------------------------------

    def _load_sdk_entries(self) -> None:
        """Load SDK entries from settings, detecting versions at runtime."""
        self._sdk_entries = []
        for path in self._settings.sdk_paths:
            ver = detect_sdk_version(path) or "?"
            self._sdk_entries.append((path, ver))

    def _sdk_dropdown_values(self) -> list[str]:
        """Build the list of dropdown display values."""
        values = [_NO_SDK_LABEL]
        for path, ver in self._sdk_entries:
            values.append(f"{ver} — {path}")
        return values

    def _add_sdk(self) -> None:
        """Open folder dialog to add a new SDK path."""
        if self._is_busy():
            return
        folder = filedialog.askdirectory(title="Select Ren'Py SDK Folder")
        if not folder:
            return
        # Check for duplicates
        existing_paths = {p for p, _ in self._sdk_entries}
        if folder in existing_paths:
            self._sdk_note.set("SDK already registered.")
            self._sdk_note_label.configure(text_color=TEXT_DIM)
            return
        if not validate_sdk_path(folder):
            self._sdk_note.set("Invalid SDK path — missing renpy/ or Python binary.")
            self._sdk_note_label.configure(text_color="#DC3545")
            return
        ver = detect_sdk_version(folder) or "?"
        self._sdk_entries.append((folder, ver))
        self._refresh_sdk_dropdown()
        # Auto-select the newly added SDK
        self._sdk_dropdown_var.set(f"{ver} — {folder}")
        self._sdk_note.set(f"Added Ren'Py {ver} SDK.")
        self._sdk_note_label.configure(text_color="#28A745")
        self._update_sdk_auto_note()

    def _remove_sdk(self) -> None:
        """Remove the currently selected SDK from the list."""
        if self._is_busy():
            return
        selected = self._sdk_dropdown_var.get()
        if selected == _NO_SDK_LABEL:
            return
        # Find and remove
        self._sdk_entries = [(p, v) for p, v in self._sdk_entries if f"{v} — {p}" != selected]
        self._refresh_sdk_dropdown()
        self._sdk_dropdown_var.set(_NO_SDK_LABEL)
        self._sdk_note.set("SDK removed.")
        self._sdk_note_label.configure(text_color=TEXT_DIM)
        self._update_sdk_auto_note()

    def _refresh_sdk_dropdown(self) -> None:
        """Rebuild the dropdown menu with current SDK entries."""
        values = self._sdk_dropdown_values()
        self._sdk_dropdown.configure(values=values)

    def _on_sdk_dropdown_change(self, _value: str) -> None:
        """Called when the SDK dropdown selection changes."""
        self._update_sdk_auto_note()

    def _update_sdk_auto_note(self) -> None:
        """Update the auto-selection note based on game version and available SDKs."""
        game_path = self._path_var.get().strip()
        if not game_path or not self._sdk_entries:
            if not self._sdk_entries:
                self._sdk_note.set("")
            return

        game_ver = detect_renpy_version(game_path)
        sdk_paths = [p for p, _ in self._sdk_entries]
        matched = select_sdk(game_ver, sdk_paths)

        if game_ver and matched:
            matched_ver = detect_sdk_version(matched) or "?"
            self._sdk_note.set(
                f"Game uses Ren'Py {format_version(game_ver)} — SDK {matched_ver} will be used"
            )
            self._sdk_note_label.configure(text_color="#28A745")
        elif game_ver:
            self._sdk_note.set(
                f"No SDK for Ren'Py {game_ver[0]}.x — regex parser will be used"
            )
            self._sdk_note_label.configure(text_color=TEXT_DIM)
        else:
            self._sdk_note.set("Could not detect game version")
            self._sdk_note_label.configure(text_color=TEXT_DIM)

    def _resolve_sdk_for_analysis(self, game_path: str) -> str | None:
        """Resolve which SDK to use for a given game path.

        If the dropdown is set to a specific SDK, use that one.
        Otherwise, auto-select based on game version.
        """
        selected = self._sdk_dropdown_var.get()
        if selected != _NO_SDK_LABEL:
            # User explicitly selected an SDK
            for path, ver in self._sdk_entries:
                if f"{ver} — {path}" == selected:
                    return path

        # Auto-select: match game version to SDK major version
        if not self._sdk_entries:
            return None
        game_ver = detect_renpy_version(game_path)
        sdk_paths = [p for p, _ in self._sdk_entries]
        return select_sdk(game_ver, sdk_paths)

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_header(self) -> None:
        """Row 0: Title header."""
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 0))
        header.grid_propagate(False)

        ctk.CTkLabel(
            header,
            text="Ren'Py Analyzer",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM,
        ).pack(side="left", padx=(8, 0), pady=(6, 0))

    def _build_input_panel(self) -> None:
        """Row 1: Game path + SDK manager."""
        panel = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=8)
        panel.grid(row=1, column=0, sticky="ew", padx=20, pady=(8, 0))
        panel.grid_columnconfigure(1, weight=1)

        # Game path row
        ctk.CTkLabel(
            panel, text="Game Path:", font=ctk.CTkFont(size=12),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(12, 6), pady=(10, 2))

        self._path_entry = ctk.CTkEntry(
            panel, textvariable=self._path_var,
            placeholder_text="Select a Ren'Py project folder...",
            fg_color=MIDNIGHT_BG, border_color=PANEL_BORDER, text_color=TEXT_PRIMARY,
        )
        self._path_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=(10, 2))

        self._browse_game_btn = ctk.CTkButton(
            panel, text="Browse...", width=80, height=28,
            fg_color=PANEL_LIGHTER, hover_color=PANEL_BORDER,
            text_color=TEXT_PRIMARY, command=self._browse_folder,
        )
        self._browse_game_btn.grid(row=0, column=2, columnspan=2, padx=(4, 12), pady=(10, 2))

        # Game dir note
        ctk.CTkLabel(
            panel, textvariable=self._game_dir_note,
            font=ctk.CTkFont(size=10), text_color="#28A745",
        ).grid(row=1, column=1, sticky="w", padx=4, pady=(0, 0))

        # SDK row: label + dropdown + Add + Remove
        ctk.CTkLabel(
            panel, text="SDK:", font=ctk.CTkFont(size=12),
            text_color=TEXT_PRIMARY,
        ).grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(4, 2))

        self._sdk_dropdown = ctk.CTkOptionMenu(
            panel,
            values=self._sdk_dropdown_values(),
            variable=self._sdk_dropdown_var,
            command=self._on_sdk_dropdown_change,
            fg_color=MIDNIGHT_BG,
            button_color=PANEL_LIGHTER,
            button_hover_color=PANEL_BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=12),
            dropdown_fg_color=PANEL_BG,
            dropdown_hover_color=PANEL_LIGHTER,
            dropdown_text_color=TEXT_PRIMARY,
            dynamic_resizing=False,
        )
        self._sdk_dropdown.grid(row=2, column=1, sticky="ew", padx=4, pady=(4, 2))

        self._add_sdk_btn = ctk.CTkButton(
            panel, text="Add SDK...", width=90, height=28,
            fg_color=PANEL_LIGHTER, hover_color=PANEL_BORDER,
            text_color=TEXT_PRIMARY, command=self._add_sdk,
        )
        self._add_sdk_btn.grid(row=2, column=2, padx=(4, 2), pady=(4, 2))

        self._remove_sdk_btn = ctk.CTkButton(
            panel, text="Remove", width=70, height=28,
            fg_color=PANEL_LIGHTER, hover_color="#DC3545",
            text_color=TEXT_PRIMARY, command=self._remove_sdk,
        )
        self._remove_sdk_btn.grid(row=2, column=3, padx=(2, 12), pady=(4, 2))

        # SDK note
        self._sdk_note_label = ctk.CTkLabel(
            panel, textvariable=self._sdk_note,
            font=ctk.CTkFont(size=10), text_color=TEXT_DIM,
        )
        self._sdk_note_label.grid(row=3, column=1, sticky="w", padx=4, pady=(0, 8))

    def _build_checks_panel(self) -> None:
        """Row 2: Check toggles in a 5x3 grid."""
        panel = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=8)
        panel.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 0))

        ctk.CTkLabel(
            panel, text="Checks", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, columnspan=5, sticky="w", padx=12, pady=(8, 4))

        cols = 5
        for idx, name in enumerate(ALL_CHECKS.keys()):
            saved = self._settings.check_toggles.get(name, True)
            var = BooleanVar(value=saved)
            self._check_vars[name] = var
            r = 1 + idx // cols
            c = idx % cols
            ctk.CTkCheckBox(
                panel,
                text=_CHECK_LABELS.get(name, name),
                variable=var,
                font=ctk.CTkFont(size=12),
                fg_color=ACCENT_BLUE,
                border_color=PANEL_BORDER,
                hover_color=PANEL_LIGHTER,
                text_color=TEXT_PRIMARY,
                width=20,
            ).grid(row=r, column=c, sticky="w", padx=(12, 4), pady=3)

        for c in range(cols):
            panel.grid_columnconfigure(c, weight=1)

        # Bottom padding
        max_row = 1 + (len(ALL_CHECKS) - 1) // cols
        ctk.CTkLabel(panel, text="", height=4).grid(row=max_row + 1, column=0)

    def _build_action_bar(self) -> None:
        """Row 3: Analyze button + severity filters + Export PDF."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=20, pady=(8, 0))

        # Analyze button
        self._analyze_btn = ctk.CTkButton(
            bar, text="Analyze", font=ctk.CTkFont(size=13, weight="bold"),
            width=110, height=34, fg_color=ACCENT_BLUE, hover_color="#1858C4",
            text_color="#FFFFFF", command=self._start_analysis,
        )
        self._analyze_btn.pack(side="left", padx=(0, 12))

        # Severity filter buttons
        for sev in Severity:
            color = SEVERITY_COLORS[sev]
            btn = ctk.CTkButton(
                bar,
                text=f"{sev.name} (0)",
                width=110, height=32,
                font=ctk.CTkFont(size=12),
                fg_color=color if self._severity_active[sev] else PANEL_LIGHTER,
                hover_color=PANEL_BORDER,
                text_color="#FFFFFF" if self._severity_active[sev] else TEXT_DIM,
                command=lambda s=sev: self._toggle_severity(s),
            )
            btn.pack(side="left", padx=2)
            self._severity_buttons[sev] = btn

        # Export PDF button
        self._export_btn = ctk.CTkButton(
            bar, text="Export PDF", width=110, height=32,
            font=ctk.CTkFont(size=12), fg_color=PANEL_LIGHTER,
            hover_color=PANEL_BORDER, text_color=TEXT_PRIMARY,
            state="disabled", command=self._export_pdf,
        )
        self._export_btn.pack(side="right")

    def _build_results(self) -> None:
        """Row 4: Treeview table (expands) + progress overlay."""
        # Container frame for both treeview and progress
        self._results_container = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=8)
        self._results_container.grid(row=4, column=0, sticky="nsew", padx=20, pady=(8, 0))
        self._results_container.grid_rowconfigure(0, weight=1)
        self._results_container.grid_columnconfigure(0, weight=1)

        # --- Treeview frame ---
        self._tree_frame = tk.Frame(self._results_container, bg=PANEL_BG)
        self._tree_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._tree_frame.grid_rowconfigure(0, weight=1)
        self._tree_frame.grid_columnconfigure(0, weight=1)

        col_ids = [c[0] for c in _TREE_COLUMNS]
        self._tree = ttk.Treeview(
            self._tree_frame,
            columns=col_ids,
            show="headings",
            selectmode="extended",
        )

        for col_id, heading, width, stretch, anchor in _TREE_COLUMNS:
            self._tree.heading(
                col_id, text=heading,
                command=lambda c=col_id: self._sort_by_column(c),  # type: ignore[misc]
            )
            self._tree.column(col_id, width=width, stretch=stretch, anchor=anchor)  # type: ignore[call-overload]

        self._tree.grid(row=0, column=0, sticky="nsew")

        # Scrollbar (ttk native — correct pairing with ttk.Treeview)
        scrollbar = ttk.Scrollbar(self._tree_frame, orient="vertical", command=self._tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=scrollbar.set)

        # Bind selection + copy
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Control-c>", self._copy_selected_findings)
        self._tree.bind("<Control-a>", self._select_all_findings)

        # --- Progress overlay ---
        self._progress_frame = ctk.CTkFrame(self._results_container, fg_color=PANEL_BG)
        # Not gridded initially — shown only during analysis

        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="Preparing...",
            font=ctk.CTkFont(size=12), text_color=TEXT_PRIMARY,
        )
        self._progress_label.pack(fill="x", padx=20, pady=(40, 4))

        self._progress_bar = ctk.CTkProgressBar(
            self._progress_frame, width=400,
            progress_color=ACCENT_BLUE, fg_color=PANEL_LIGHTER,
        )
        self._progress_bar.pack(fill="x", padx=40, pady=(4, 8))
        self._progress_bar.set(0)

        self._cancel_btn = ctk.CTkButton(
            self._progress_frame, text="Cancel", width=90, height=30,
            fg_color="#DC3545", hover_color="#A71D2A", text_color="#FFFFFF",
            command=self._request_cancel,
        )
        self._cancel_btn.pack(pady=(4, 20))

    def _build_detail_panel(self) -> None:
        """Row 5: Selected finding detail (selectable/copyable text)."""
        self._detail_frame = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=8, height=120)
        self._detail_frame.grid(row=5, column=0, sticky="ew", padx=20, pady=(8, 0))
        self._detail_frame.grid_propagate(False)
        self._detail_frame.grid_columnconfigure(0, weight=1)
        self._detail_frame.grid_rowconfigure(0, weight=1)

        self._detail_text = ctk.CTkTextbox(
            self._detail_frame,
            font=ctk.CTkFont(size=14),
            fg_color=PANEL_BG,
            text_color=TEXT_PRIMARY,
            border_width=0,
            corner_radius=0,
            wrap="word",
            activate_scrollbars=False,
        )
        self._detail_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)
        self._detail_text.insert("1.0", "Select a finding to see details")
        self._detail_text.configure(state="disabled")

        # Text tags for styling parts of the detail content
        self._detail_text.tag_config("title", foreground=TEXT_DIM)
        self._detail_text.tag_config("suggestion", foreground="#28A745")
        for sev in Severity:
            self._detail_text.tag_config(
                f"title_{sev.name}", foreground=SEVERITY_COLORS[sev],
            )

    def _build_status_bar(self) -> None:
        """Row 6: Status text."""
        self._status_var = StringVar(value="Ready")
        status_bar = ctk.CTkFrame(self, fg_color="transparent", height=28)
        status_bar.grid(row=6, column=0, sticky="ew", padx=20, pady=(4, 6))
        status_bar.grid_propagate(False)

        ctk.CTkLabel(
            status_bar, textvariable=self._status_var,
            font=ctk.CTkFont(size=11), text_color=TEXT_DIM, anchor="w",
        ).pack(fill="x", side="left")

    # -----------------------------------------------------------------------
    # Treeview styling (must use ttk.Style with 'default' theme)
    # -----------------------------------------------------------------------

    def _configure_treeview_style(self) -> None:
        """Apply midnight colors to ttk.Treeview via the 'default' theme.

        Called synchronously in __init__ before widgets are built.
        Uses the global 'default' theme because OS themes (vista, clam, etc.)
        ignore custom background/foreground color settings on Treeview.
        """
        style = ttk.Style()
        style.theme_use("default")

        style.configure(
            "Treeview",
            background=PANEL_BG,
            foreground=TEXT_PRIMARY,
            fieldbackground=PANEL_BG,
            borderwidth=0,
            font=("Segoe UI", 14),
            rowheight=32,
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL_LIGHTER,
            foreground=TEXT_PRIMARY,
            borderwidth=0,
            font=("Segoe UI", 14, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_BLUE)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", PANEL_BORDER)],
        )

        # Scrollbar styling
        style.configure(
            "Vertical.TScrollbar",
            background=PANEL_LIGHTER,
            troughcolor=PANEL_BG,
            borderwidth=0,
            arrowcolor=TEXT_DIM,
        )

    def _configure_treeview_tags(self) -> None:
        """Configure severity + alternating row color tags on the Treeview."""
        for sev in Severity:
            color = SEVERITY_COLORS[sev]
            self._tree.tag_configure(f"{sev.name}_even", foreground=color, background=PANEL_BG)
            self._tree.tag_configure(f"{sev.name}_odd", foreground=color, background=PANEL_LIGHTER)


    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _is_busy(self) -> bool:
        """Return True if analysis or export is in progress."""
        return self._analysis_thread is not None and self._analysis_thread.is_alive()

    def _browse_folder(self) -> None:
        if self._is_busy():
            return
        folder = filedialog.askdirectory(title="Select Ren'Py Project Folder")
        if folder:
            self._path_var.set(folder)
            game_sub = Path(folder) / "game"
            if game_sub.is_dir():
                self._game_dir_note.set("game/ subfolder detected — will scan automatically.")
            else:
                self._game_dir_note.set("")
            self._update_sdk_auto_note()

    def _start_analysis(self) -> None:
        # Guard against double-click / re-entrant calls
        if self._is_busy():
            return

        project_path = self._path_var.get().strip()
        if not project_path:
            self._status_var.set("Please select a project folder first.")
            return
        if not Path(project_path).is_dir():
            self._status_var.set("Selected path is not a valid directory.")
            return

        enabled = [name for name, var in self._check_vars.items() if var.get()]
        if not enabled:
            self._status_var.set("Please enable at least one check.")
            return

        # Resolve SDK before starting the thread
        self._resolved_sdk_path = self._resolve_sdk_for_analysis(project_path)

        self._analyze_btn.configure(state="disabled")
        self._export_btn.configure(state="disabled")
        self._browse_game_btn.configure(state="disabled")
        self._add_sdk_btn.configure(state="disabled")
        self._remove_sdk_btn.configure(state="disabled")
        self._tree.delete(*self._tree.get_children())

        self._cancel_event.clear()
        self._cancel_btn.configure(state="normal")
        self._progress_bar.set(0)
        self._progress_label.configure(text="Parsing project files...")

        # Swap treeview for progress overlay
        self._tree_frame.grid_remove()
        self._progress_frame.grid(row=0, column=0, sticky="nsew")

        self._analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(project_path, enabled),
            daemon=True,
        )
        self._analysis_thread.start()

    def _run_analysis(self, project_path: str, enabled_checks: list[str]) -> None:
        sdk_path = self._resolved_sdk_path
        try:
            findings = run_analysis(
                project_path,
                checks=enabled_checks,
                on_progress=lambda msg, frac: self.after(0, self._update_progress, msg, frac),
                cancel_check=self._cancel_event.is_set,
                sdk_path=sdk_path,
            )
            if self._cancel_event.is_set():
                self.after(0, self._analysis_cancelled)
                return
            self.after(100, self._analysis_complete, findings, project_path)
        except Exception as exc:
            logger.exception("Analysis failed")
            error_msg = str(exc) or f"{type(exc).__name__}: (no details available)"
            with contextlib.suppress(Exception):
                self.after(0, self._analysis_failed, error_msg)

    # -----------------------------------------------------------------------
    # GUI callbacks
    # -----------------------------------------------------------------------

    def _update_progress(self, text: str, fraction: float) -> None:
        self._progress_label.configure(text=text)
        self._progress_bar.set(fraction)
        self._status_var.set(text)

    def _restore_ui_after_analysis(self) -> None:
        """Common UI reset after analysis ends (complete, cancelled, or failed)."""
        self._progress_frame.grid_remove()
        self._tree_frame.grid(row=0, column=0, sticky="nsew")
        self._analyze_btn.configure(state="normal")
        self._browse_game_btn.configure(state="normal")
        self._add_sdk_btn.configure(state="normal")
        self._remove_sdk_btn.configure(state="normal")

    def _analysis_complete(self, findings: list[Finding], project_path: str) -> None:
        self._findings = findings
        self._project_path = project_path

        self._restore_ui_after_analysis()
        self._export_btn.configure(state="normal" if findings else "disabled")

        # Update severity counts
        self._severity_counts = Counter(f.severity for f in findings)
        self._update_severity_buttons()

        # Populate table
        self._apply_filters_and_sort()

        # Status bar
        total = len(findings)
        parser_label = "(SDK parser)" if self._resolved_sdk_path else "(regex parser)"
        if total == 0:
            self._status_var.set(f"Analysis complete {parser_label} — no issues found!")
        else:
            parts = []
            for sev in Severity:
                c = self._severity_counts.get(sev, 0)
                if c > 0:
                    parts.append(f"{c} {sev.name.lower()}")
            self._status_var.set(
                f"Analysis complete {parser_label} — {total} findings ({', '.join(parts)})"
            )

    def _request_cancel(self) -> None:
        self._cancel_event.set()
        self._cancel_btn.configure(state="disabled")
        self._progress_label.configure(text="Cancelling...")

    def _analysis_cancelled(self) -> None:
        self._restore_ui_after_analysis()
        self._severity_counts = {}
        self._update_severity_buttons()
        self._status_var.set("Analysis cancelled.")

    def _analysis_failed(self, error_msg: str) -> None:
        self._restore_ui_after_analysis()
        self._severity_counts = {}
        self._update_severity_buttons()
        self._status_var.set(f"Error: {error_msg}")

    # -----------------------------------------------------------------------
    # Treeview: populate, sort, filter
    # -----------------------------------------------------------------------

    def _apply_filters_and_sort(self) -> None:
        """Rebuild the Treeview contents based on current filters and sort state."""
        # Filter
        self._filtered_findings = [
            f for f in self._findings if self._severity_active.get(f.severity, True)
        ]

        # Sort
        col = self._sort_column
        reverse = not self._sort_ascending

        if col == "severity":
            self._filtered_findings.sort(key=lambda f: (f.severity, f.file.lower(), f.line), reverse=reverse)
        elif col == "check":
            self._filtered_findings.sort(key=lambda f: f.check_name.lower(), reverse=reverse)
        elif col == "description":
            self._filtered_findings.sort(key=lambda f: f.title.lower(), reverse=reverse)
        elif col == "file":
            self._filtered_findings.sort(key=lambda f: (f.file.lower(), f.line), reverse=reverse)
        elif col == "line":
            self._filtered_findings.sort(key=lambda f: f.line, reverse=reverse)

        # Hide tree during rebuild to prevent flicker with large datasets
        self._tree.grid_remove()
        self._tree.delete(*self._tree.get_children())
        for idx, f in enumerate(self._filtered_findings):
            parity = "even" if idx % 2 == 0 else "odd"
            tag = f"{f.severity.name}_{parity}"
            self._tree.insert(
                "", "end",
                iid=str(idx),
                values=(f.severity.name, f.check_name, f.title, f.file, f.line),
                tags=(tag,),
            )
        self._tree.grid(row=0, column=0, sticky="nsew")

        # Clear selection to prevent stale iid → wrong finding in detail panel
        self._tree.selection_set([])
        self._detail_text.configure(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.insert("1.0", "Select a finding to see details", "title")
        self._detail_text.configure(state="disabled")

    def _sort_by_column(self, col: str) -> None:
        """Toggle sort direction on column click."""
        if self._sort_column == col:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = col
            self._sort_ascending = True
        self._apply_filters_and_sort()

    def _toggle_severity(self, sev: Severity) -> None:
        """Toggle a severity filter on/off and refresh the table."""
        self._severity_active[sev] = not self._severity_active[sev]
        self._update_severity_buttons()
        self._apply_filters_and_sort()

    def _update_severity_buttons(self) -> None:
        """Update severity button text/colors to reflect current counts and filter state."""
        for sev, btn in self._severity_buttons.items():
            count = self._severity_counts.get(sev, 0)
            active = self._severity_active[sev]
            color = SEVERITY_COLORS[sev]
            btn.configure(
                text=f"{sev.name} ({count})",
                fg_color=color if active else PANEL_LIGHTER,
                text_color="#FFFFFF" if active else TEXT_DIM,
            )

    def _get_selected_findings(self) -> list[Finding]:
        """Return Finding objects for all selected treeview rows."""
        findings: list[Finding] = []
        for iid in self._tree.selection():
            try:
                idx = int(iid)
            except (ValueError, IndexError):
                continue
            if 0 <= idx < len(self._filtered_findings):
                findings.append(self._filtered_findings[idx])
        return findings

    def _on_tree_select(self, _event: tk.Event) -> None:
        """Show selected finding(s) detail in the panel below."""
        selected = self._get_selected_findings()
        if not selected:
            return

        self._detail_text.configure(state="normal")
        self._detail_text.delete("1.0", "end")

        if len(selected) == 1:
            f = selected[0]
            title_tag = f"title_{f.severity.name}"
            self._detail_text.insert("end", f"[{f.severity.name}] {f.title}", title_tag)
            if f.description:
                self._detail_text.insert("end", f"\n\n{f.description}")
            if f.suggestion:
                self._detail_text.insert("end", f"\n\nSuggestion: {f.suggestion}", "suggestion")
        else:
            self._detail_text.insert(
                "end",
                f"{len(selected)} findings selected — Ctrl+C to copy\n\n",
                "title",
            )
            for i, f in enumerate(selected):
                if i > 0:
                    self._detail_text.insert("end", "\n")
                title_tag = f"title_{f.severity.name}"
                self._detail_text.insert(
                    "end",
                    f"[{f.severity.name}] {f.title}  —  {f.file}:{f.line}",
                    title_tag,
                )

        self._detail_text.configure(state="disabled")

    def _format_finding_text(self, f: Finding) -> str:
        """Format a single finding as copyable plain text."""
        lines = [f"[{f.severity.name}] {f.title}  —  {f.file}:{f.line}"]
        if f.description:
            lines.append(f.description)
        if f.suggestion:
            lines.append(f"Suggestion: {f.suggestion}")
        return "\n".join(lines)

    def _copy_selected_findings(self, _event: tk.Event) -> str:
        """Copy all selected findings to clipboard as formatted text."""
        selected = self._get_selected_findings()
        if not selected:
            return "break"
        text = "\n\n".join(self._format_finding_text(f) for f in selected)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status_var.set(f"Copied {len(selected)} finding(s) to clipboard.")
        return "break"

    def _select_all_findings(self, _event: tk.Event) -> str:
        """Select all rows in the treeview."""
        all_items = self._tree.get_children()
        if all_items:
            self._tree.selection_set(all_items)
        return "break"

    # -----------------------------------------------------------------------
    # PDF export
    # -----------------------------------------------------------------------

    def _export_pdf(self) -> None:
        if not self._findings:
            self._status_var.set("No findings to export.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Save PDF Report",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialfile="renpy_analysis_report.pdf",
        )
        if not output_path:
            return

        self._status_var.set("Generating PDF report...")
        self._export_btn.configure(state="disabled")
        self._analyze_btn.configure(state="disabled")

        # Snapshot findings for thread safety — main thread may clear the list
        findings_snapshot = list(self._findings)
        project_path = self._project_path

        threading.Thread(
            target=self._run_pdf_export,
            args=(output_path, findings_snapshot, project_path),
            daemon=True,
        ).start()

    def _run_pdf_export(self, output_path: str, findings: list[Finding], project_path: str) -> None:
        try:
            game_name = Path(project_path).name if project_path else "Ren'Py Project"
            generate_pdf(
                findings=findings,
                output_path=output_path,
                game_name=game_name,
                game_path=project_path,
            )
            logger.info("PDF exported to %s", output_path)
            with contextlib.suppress(Exception):
                self.after(0, self._pdf_export_done, output_path, None)
        except Exception as exc:
            logger.exception("PDF export failed")
            error_msg = str(exc) or f"{type(exc).__name__}: (no details available)"
            with contextlib.suppress(Exception):
                self.after(0, self._pdf_export_done, output_path, error_msg)

    def _pdf_export_done(self, output_path: str, error: str | None) -> None:
        self._export_btn.configure(state="normal")
        self._analyze_btn.configure(state="normal")
        if error:
            self._status_var.set(f"PDF export failed: {error}")
        else:
            self._status_var.set(f"PDF saved to {output_path}")

    # -----------------------------------------------------------------------
    # Settings persistence + clean shutdown
    # -----------------------------------------------------------------------

    def _save_settings(self) -> None:
        """Persist current state to settings file."""
        try:
            self._settings.game_path = self._path_var.get()
            self._settings.sdk_paths = [p for p, _ in self._sdk_entries]
        except Exception:
            logger.debug("Could not read path variables during save", exc_info=True)

        try:
            self._settings.window_geometry = self.geometry()
        except Exception:
            logger.debug("Could not read window geometry during save", exc_info=True)

        try:
            self._settings.check_toggles = {
                name: var.get() for name, var in self._check_vars.items()
            }
        except Exception:
            logger.debug("Could not read check toggles during save", exc_info=True)

        self._settings.severity_filters = {
            sev.name: active for sev, active in self._severity_active.items()
        }
        self._settings.sort_column = self._sort_column
        self._settings.sort_ascending = self._sort_ascending
        self._settings.save()

    def destroy(self) -> None:
        """Override destroy to save settings and ensure clean exit."""
        try:
            self._save_settings()
        except Exception:
            logger.debug("Settings save failed on exit", exc_info=True)
        os._exit(0)


def main() -> None:
    """Entry point for the GUI application."""
    setup_logging(verbose=None)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = RenpyAnalyzerApp()
    app.mainloop()
