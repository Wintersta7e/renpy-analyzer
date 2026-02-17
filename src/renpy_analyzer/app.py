"""Ren'Py Analyzer GUI -- CustomTkinter desktop application."""

from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog

import customtkinter as ctk

from . import __version__
from .checks import ALL_CHECKS
from .models import Finding, Severity
from .project import load_project
from .report.pdf import generate_pdf

# ---------------------------------------------------------------------------
# Severity colours for GUI display
# ---------------------------------------------------------------------------

SEVERITY_COLORS: dict[Severity, str] = {
    Severity.CRITICAL: "#DC3545",
    Severity.HIGH: "#FD7E14",
    Severity.MEDIUM: "#FFC107",
    Severity.LOW: "#28A745",
    Severity.STYLE: "#6C757D",
}

# Human-friendly labels for checks shown in the GUI
_CHECK_DESCRIPTIONS: dict[str, str] = {
    "Labels": "Labels & Jumps",
    "Variables": "Variables",
    "Logic": "Logic Errors",
    "Menus": "Menus",
    "Assets": "Assets",
    "Characters": "Characters",
}


class RenpyAnalyzerApp(ctk.CTk):
    """Main application window for Ren'Py Analyzer."""

    def __init__(self) -> None:
        super().__init__()

        # -- Window setup --
        self.title("Ren'Py Analyzer")
        self.geometry("900x700")
        self.minsize(720, 560)

        # State
        self._path_var = StringVar(value="")
        self._check_vars: dict[str, BooleanVar] = {}
        self._findings: list[Finding] = []
        self._analysis_thread: threading.Thread | None = None
        self._game_dir_note = StringVar(value="")

        # Build all frames
        self._build_header()
        self._build_path_selector()
        self._build_checks()
        self._build_action_buttons()
        self._build_progress()
        self._build_results()
        self._build_export()
        self._build_status_bar()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_header(self) -> None:
        """App title and version at the top."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=(15, 5))

        title_label = ctk.CTkLabel(
            frame,
            text="Ren'Py Analyzer",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(side="left")

        version_label = ctk.CTkLabel(
            frame,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        version_label.pack(side="left", padx=(10, 0), pady=(8, 0))

    def _build_path_selector(self) -> None:
        """Folder path entry + browse button."""
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=20, pady=(5, 5))

        label = ctk.CTkLabel(frame, text="Project Path:", font=ctk.CTkFont(size=13))
        label.pack(side="left", padx=(10, 5), pady=10)

        self._path_entry = ctk.CTkEntry(
            frame,
            textvariable=self._path_var,
            placeholder_text="Select a Ren'Py project folder...",
            width=500,
        )
        self._path_entry.pack(side="left", fill="x", expand=True, padx=5, pady=10)

        browse_btn = ctk.CTkButton(
            frame,
            text="Browse...",
            width=100,
            command=self._browse_folder,
        )
        browse_btn.pack(side="right", padx=(5, 10), pady=10)

        # Auto-detection note (below the path row)
        self._note_label = ctk.CTkLabel(
            self,
            textvariable=self._game_dir_note,
            font=ctk.CTkFont(size=11),
            text_color="#28A745",
        )
        self._note_label.pack(fill="x", padx=35, pady=(0, 2))

    def _build_checks(self) -> None:
        """Checkboxes for each check module in a 2x3 grid."""
        outer = ctk.CTkFrame(self)
        outer.pack(fill="x", padx=20, pady=(5, 5))

        heading = ctk.CTkLabel(
            outer,
            text="Checks to Run:",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        heading.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))

        check_names = list(ALL_CHECKS.keys())
        for idx, name in enumerate(check_names):
            var = BooleanVar(value=True)
            self._check_vars[name] = var
            display = _CHECK_DESCRIPTIONS.get(name, name)
            cb = ctk.CTkCheckBox(
                outer,
                text=display,
                variable=var,
                font=ctk.CTkFont(size=12),
            )
            row = 1 + idx // 3
            col = idx % 3
            cb.grid(row=row, column=col, sticky="w", padx=(15, 10), pady=4)

        # Configure columns to distribute evenly
        for c in range(3):
            outer.columnconfigure(c, weight=1)

        # Padding at bottom of frame
        spacer = ctk.CTkLabel(outer, text="")
        spacer.grid(row=3, column=0, pady=(0, 6))

    def _build_action_buttons(self) -> None:
        """Central 'Analyze Game' button."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=(5, 5))

        self._analyze_btn = ctk.CTkButton(
            frame,
            text="Analyze Game",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=40,
            width=200,
            command=self._start_analysis,
        )
        self._analyze_btn.pack(pady=5)

    def _build_progress(self) -> None:
        """Progress bar + status label (initially hidden)."""
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        # Not packed initially -- shown when analysis starts.

        self._progress_label = ctk.CTkLabel(
            self._progress_frame,
            text="Preparing...",
            font=ctk.CTkFont(size=12),
        )
        self._progress_label.pack(fill="x", padx=10, pady=(4, 2))

        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, width=400)
        self._progress_bar.pack(fill="x", padx=40, pady=(2, 6))
        self._progress_bar.set(0)

    def _build_results(self) -> None:
        """Scrollable results frame with summary and finding rows."""
        # Summary bar
        self._summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        # Not packed initially.

        self._summary_label = ctk.CTkLabel(
            self._summary_frame,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._summary_label.pack(fill="x", padx=20, pady=(6, 2))

        # Scrollable results area
        self._results_frame = ctk.CTkScrollableFrame(
            self,
            label_text="Findings",
            label_font=ctk.CTkFont(size=12, weight="bold"),
        )
        # Not packed initially.

    def _build_export(self) -> None:
        """Export PDF button (disabled until analysis finishes)."""
        self._export_frame = ctk.CTkFrame(self, fg_color="transparent")
        # Not packed initially.

        self._export_btn = ctk.CTkButton(
            self._export_frame,
            text="Export PDF Report",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            width=180,
            state="disabled",
            command=self._export_pdf,
        )
        self._export_btn.pack(pady=6)

    def _build_status_bar(self) -> None:
        """Bottom status bar."""
        self._status_var = StringVar(value="Ready")
        self._status_bar = ctk.CTkLabel(
            self,
            textvariable=self._status_var,
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._status_bar.pack(fill="x", side="bottom", padx=20, pady=(2, 8))

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _browse_folder(self) -> None:
        """Open a folder selection dialog."""
        folder = filedialog.askdirectory(title="Select Ren'Py Project Folder")
        if folder:
            self._path_var.set(folder)
            self._detect_game_dir(folder)

    def _detect_game_dir(self, path: str) -> None:
        """Check if the selected folder contains a game/ subfolder."""
        game_sub = Path(path) / "game"
        if game_sub.is_dir():
            self._game_dir_note.set("game/ subfolder detected -- will scan automatically.")
        else:
            self._game_dir_note.set("")

    def _start_analysis(self) -> None:
        """Validate inputs and launch analysis in background thread."""
        project_path = self._path_var.get().strip()
        if not project_path:
            self._status_var.set("Please select a project folder first.")
            return

        if not Path(project_path).is_dir():
            self._status_var.set("Selected path is not a valid directory.")
            return

        # Determine which checks are enabled
        enabled = [name for name, var in self._check_vars.items() if var.get()]
        if not enabled:
            self._status_var.set("Please enable at least one check.")
            return

        # Disable the button to prevent double-clicks
        self._analyze_btn.configure(state="disabled")
        self._export_btn.configure(state="disabled")
        self._findings.clear()

        # Show progress
        self._progress_frame.pack(fill="x", padx=20, pady=(2, 2), before=self._status_bar)
        self._progress_bar.set(0)
        self._progress_label.configure(text="Parsing project files...")

        # Hide old results
        self._summary_frame.pack_forget()
        self._results_frame.pack_forget()
        self._export_frame.pack_forget()

        # Clear old finding widgets from scrollable frame
        for widget in self._results_frame.winfo_children():
            widget.destroy()

        # Launch background thread
        self._analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(project_path, enabled),
            daemon=True,
        )
        self._analysis_thread.start()

    def _run_analysis(self, project_path: str, enabled_checks: list[str]) -> None:
        """Run analysis in a background thread (do NOT touch GUI directly)."""
        try:
            # Phase 0: parse project
            self.after(0, self._update_progress, "Parsing project files...", 0.0)
            project = load_project(project_path)

            file_count = len(project.files)
            self.after(0, self._update_progress, f"Parsed {file_count} .rpy file(s).", 0.1)

            total_checks = len(enabled_checks)
            findings: list[Finding] = []

            for idx, check_name in enumerate(enabled_checks):
                fraction = 0.1 + 0.85 * (idx / total_checks)
                status_msg = f"Running check: {check_name}..."
                self.after(0, self._update_progress, status_msg, fraction)

                check_fn = ALL_CHECKS[check_name]
                results = check_fn(project)
                findings.extend(results)

            # Sort findings by severity (most severe first)
            findings.sort(key=lambda f: f.severity)

            self.after(0, self._update_progress, "Analysis complete.", 1.0)
            self.after(100, self._analysis_complete, findings, project_path)

        except Exception as exc:
            self.after(0, self._analysis_failed, str(exc))

    # -----------------------------------------------------------------------
    # GUI update callbacks (called via self.after from thread)
    # -----------------------------------------------------------------------

    def _update_progress(self, text: str, fraction: float) -> None:
        """Update progress bar and label from the main thread."""
        self._progress_label.configure(text=text)
        self._progress_bar.set(fraction)
        self._status_var.set(text)

    def _analysis_complete(self, findings: list[Finding], project_path: str) -> None:
        """Populate results after analysis finishes."""
        self._findings = findings
        self._project_path = project_path

        # Hide progress
        self._progress_frame.pack_forget()

        # Re-enable buttons
        self._analyze_btn.configure(state="normal")
        self._export_btn.configure(state="normal")

        # Build summary text
        total = len(findings)
        counts = Counter(f.severity for f in findings)
        parts = []
        for sev in Severity:
            c = counts.get(sev, 0)
            if c > 0:
                parts.append(f"{c} {sev.name.lower()}")
        summary = f"{total} finding{'s' if total != 1 else ''}"
        if parts:
            summary += ": " + ", ".join(parts)

        self._summary_label.configure(text=summary)

        # Show summary, results, export
        self._summary_frame.pack(fill="x", padx=20, pady=(6, 0), before=self._status_bar)
        self._results_frame.pack(
            fill="both", expand=True, padx=20, pady=(4, 4),
            before=self._status_bar,
        )
        self._export_frame.pack(fill="x", padx=20, pady=(2, 2), before=self._status_bar)

        # Populate findings
        self._populate_findings(findings)

        if total == 0:
            self._status_var.set("Analysis complete -- no issues found!")
        else:
            self._status_var.set(f"Analysis complete -- {total} finding(s).")

    def _analysis_failed(self, error_msg: str) -> None:
        """Handle an analysis failure."""
        self._progress_frame.pack_forget()
        self._analyze_btn.configure(state="normal")
        self._status_var.set(f"Error: {error_msg}")

    # -----------------------------------------------------------------------
    # Result display
    # -----------------------------------------------------------------------

    def _populate_findings(self, findings: list[Finding]) -> None:
        """Create a row widget for each finding inside the scrollable frame."""
        if not findings:
            empty = ctk.CTkLabel(
                self._results_frame,
                text="No issues found -- your project looks clean!",
                font=ctk.CTkFont(size=13),
                text_color="#28A745",
            )
            empty.pack(fill="x", padx=10, pady=20)
            return

        for idx, finding in enumerate(findings):
            self._create_finding_row(finding, idx + 1)

    def _create_finding_row(self, finding: Finding, index: int) -> None:
        """Build a single finding row inside the scrollable results frame."""
        sev = finding.severity
        color = SEVERITY_COLORS[sev]

        row = ctk.CTkFrame(self._results_frame)
        row.pack(fill="x", padx=4, pady=(2, 2))

        # Left-side severity indicator (coloured bar)
        indicator = ctk.CTkFrame(row, width=6, fg_color=color, corner_radius=3)
        indicator.pack(side="left", fill="y", padx=(4, 6), pady=4)

        # Content area
        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, pady=4)

        # Top line: severity badge + title
        top_line = ctk.CTkFrame(content, fg_color="transparent")
        top_line.pack(fill="x", anchor="w")

        badge = ctk.CTkLabel(
            top_line,
            text=f" {sev.name} ",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=color,
            text_color="white" if sev != Severity.MEDIUM else "#1a1a1a",
            corner_radius=4,
            height=20,
        )
        badge.pack(side="left", padx=(0, 6))

        title_label = ctk.CTkLabel(
            top_line,
            text=finding.title,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        title_label.pack(side="left", fill="x", expand=True)

        # Index number on the right
        idx_label = ctk.CTkLabel(
            top_line,
            text=f"#{index}",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        )
        idx_label.pack(side="right", padx=(4, 8))

        # Second line: file:line
        location = f"{finding.file}:{finding.line}"
        loc_label = ctk.CTkLabel(
            content,
            text=location,
            font=ctk.CTkFont(size=11, family="Courier"),
            text_color="gray",
            anchor="w",
        )
        loc_label.pack(fill="x", anchor="w", pady=(1, 0))

        # Third line: description (truncated if very long)
        desc_text = finding.description
        if len(desc_text) > 200:
            desc_text = desc_text[:197] + "..."
        desc_label = ctk.CTkLabel(
            content,
            text=desc_text,
            font=ctk.CTkFont(size=11),
            anchor="w",
            wraplength=700,
            justify="left",
        )
        desc_label.pack(fill="x", anchor="w", pady=(1, 0))

        # Fourth line: suggestion (if any)
        if finding.suggestion:
            sugg_text = finding.suggestion
            if len(sugg_text) > 200:
                sugg_text = sugg_text[:197] + "..."
            sugg_label = ctk.CTkLabel(
                content,
                text=f"Suggestion: {sugg_text}",
                font=ctk.CTkFont(size=10),
                text_color="#28A745",
                anchor="w",
                wraplength=700,
                justify="left",
            )
            sugg_label.pack(fill="x", anchor="w", pady=(1, 2))

    # -----------------------------------------------------------------------
    # PDF export
    # -----------------------------------------------------------------------

    def _export_pdf(self) -> None:
        """Open a save-file dialog and generate the PDF report."""
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

        try:
            project_path = getattr(self, "_project_path", "")
            game_name = Path(project_path).name if project_path else "Ren'Py Project"

            generate_pdf(
                findings=self._findings,
                output_path=output_path,
                game_name=game_name,
                game_path=project_path,
            )
            self._status_var.set(f"PDF saved to {output_path}")
        except Exception as exc:
            self._status_var.set(f"PDF export failed: {exc}")
        finally:
            self._export_btn.configure(state="normal")


def main() -> None:
    """Entry point for the GUI application."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = RenpyAnalyzerApp()
    app.mainloop()
