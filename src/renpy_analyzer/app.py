"""Ren'Py Analyzer GUI -- CustomTkinter desktop application."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog

import customtkinter as ctk

from . import __version__
from .checks import ALL_CHECKS
from .log import setup_logging
from .models import Finding, Severity
from .project import load_project
from .report.pdf import generate_pdf

logger = logging.getLogger("renpy_analyzer.app")

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

_CHECK_DESCRIPTIONS: dict[str, str] = {
    "Labels": "Labels & Jumps",
    "Variables": "Variables",
    "Logic": "Logic Errors",
    "Menus": "Menus",
    "Assets": "Assets",
    "Characters": "Characters",
    "Flow": "Unreachable Code",
}


class RenpyAnalyzerApp(ctk.CTk):
    """Main application window for Ren'Py Analyzer."""

    def __init__(self) -> None:
        super().__init__()

        self.title("Ren'Py Analyzer")
        self.geometry("900x700")
        self.minsize(720, 560)

        # State
        self._path_var = StringVar(value="")
        self._check_vars: dict[str, BooleanVar] = {}
        self._findings: list[Finding] = []
        self._analysis_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._game_dir_note = StringVar(value="")

        self._build_top_section()
        self._build_bottom_section()
        self._build_middle_section()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_top_section(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(side="top", fill="x")

        # Title
        title_frame = ctk.CTkFrame(top, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(
            title_frame, text="Ren'Py Analyzer",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            title_frame, text=f"v{__version__}",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(side="left", padx=(10, 0), pady=(8, 0))

        # Path selector
        path_frame = ctk.CTkFrame(top)
        path_frame.pack(fill="x", padx=20, pady=(5, 0))
        ctk.CTkLabel(
            path_frame, text="Project Path:", font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(10, 5), pady=10)
        self._path_entry = ctk.CTkEntry(
            path_frame, textvariable=self._path_var,
            placeholder_text="Select a Ren'Py project folder...", width=500,
        )
        self._path_entry.pack(side="left", fill="x", expand=True, padx=5, pady=10)
        ctk.CTkButton(
            path_frame, text="Browse...", width=100, command=self._browse_folder,
        ).pack(side="right", padx=(5, 10), pady=10)

        # Auto-detection note
        ctk.CTkLabel(
            top, textvariable=self._game_dir_note,
            font=ctk.CTkFont(size=11), text_color="#28A745",
        ).pack(fill="x", padx=35, pady=(0, 2))

        # Check toggles
        checks_frame = ctk.CTkFrame(top)
        checks_frame.pack(fill="x", padx=20, pady=(5, 5))
        ctk.CTkLabel(
            checks_frame, text="Checks to Run:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))

        for idx, name in enumerate(ALL_CHECKS.keys()):
            var = BooleanVar(value=True)
            self._check_vars[name] = var
            ctk.CTkCheckBox(
                checks_frame, text=_CHECK_DESCRIPTIONS.get(name, name),
                variable=var, font=ctk.CTkFont(size=12),
            ).grid(row=1 + idx // 3, column=idx % 3, sticky="w", padx=(15, 10), pady=4)
        for c in range(3):
            checks_frame.columnconfigure(c, weight=1)
        ctk.CTkLabel(checks_frame, text="").grid(row=3, column=0, pady=(0, 6))

        # Analyze button
        self._analyze_btn = ctk.CTkButton(
            top, text="Analyze Game",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=40, width=200, command=self._start_analysis,
        )
        self._analyze_btn.pack(pady=(5, 8))

    def _build_bottom_section(self) -> None:
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")

        self._status_var = StringVar(value="Ready")
        ctk.CTkLabel(
            bottom, textvariable=self._status_var,
            font=ctk.CTkFont(size=11), text_color="gray", anchor="w",
        ).pack(fill="x", side="bottom", padx=20, pady=(2, 8))

        self._export_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        self._export_btn = ctk.CTkButton(
            self._export_frame, text="Export PDF Report",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36, width=180, state="disabled", command=self._export_pdf,
        )
        self._export_btn.pack(pady=6)

    def _build_middle_section(self) -> None:
        self._middle = ctk.CTkFrame(self, fg_color="transparent")
        self._middle.pack(side="top", fill="both", expand=True, padx=20)

        # Progress (shown during analysis)
        self._progress_frame = ctk.CTkFrame(self._middle, fg_color="transparent")
        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="Preparing...", font=ctk.CTkFont(size=12),
        )
        self._progress_label.pack(fill="x", padx=10, pady=(10, 2))
        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, width=400)
        self._progress_bar.pack(fill="x", padx=40, pady=(2, 4))
        self._progress_bar.set(0)
        self._cancel_btn = ctk.CTkButton(
            self._progress_frame, text="Cancel", width=100,
            fg_color="#DC3545", hover_color="#A71D2A",
            command=self._request_cancel,
        )
        self._cancel_btn.pack(pady=(2, 8))

        # Summary label (shown after analysis)
        self._summary_label = ctk.CTkLabel(
            self._middle, text="", font=ctk.CTkFont(size=13, weight="bold"),
        )

        # Results: a single Textbox widget (fast, lightweight)
        self._results_box = ctk.CTkTextbox(
            self._middle,
            font=ctk.CTkFont(size=12, family="Courier"),
            wrap="word",
            state="disabled",
            activate_scrollbars=True,
        )
        # Configure text tags for severity colours on the underlying tk Text widget
        inner: tk.Text = self._results_box._textbox
        inner.tag_configure("severity_critical", foreground="#DC3545", font=("Courier", 11, "bold"))
        inner.tag_configure("severity_high", foreground="#FD7E14", font=("Courier", 11, "bold"))
        inner.tag_configure("severity_medium", foreground="#FFC107", font=("Courier", 11, "bold"))
        inner.tag_configure("severity_low", foreground="#28A745", font=("Courier", 11, "bold"))
        inner.tag_configure("severity_style", foreground="#6C757D", font=("Courier", 11, "bold"))
        inner.tag_configure("location", foreground="#888888", font=("Courier", 10))
        inner.tag_configure("suggestion", foreground="#28A745", font=("Courier", 10))
        inner.tag_configure("title", foreground="#FFFFFF", font=("Courier", 12, "bold"))
        inner.tag_configure("separator", foreground="#444444")

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Ren'Py Project Folder")
        if folder:
            self._path_var.set(folder)
            game_sub = Path(folder) / "game"
            if game_sub.is_dir():
                self._game_dir_note.set("game/ subfolder detected — will scan automatically.")
            else:
                self._game_dir_note.set("")

    def _start_analysis(self) -> None:
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

        self._analyze_btn.configure(state="disabled")
        self._export_btn.configure(state="disabled")
        self._findings.clear()

        # Hide old results, show progress
        self._summary_label.pack_forget()
        self._results_box.pack_forget()
        self._export_frame.pack_forget()

        self._results_box.configure(state="normal")
        self._results_box.delete("1.0", "end")
        self._results_box.configure(state="disabled")

        self._cancel_event.clear()
        self._cancel_btn.configure(state="normal")
        self._progress_bar.set(0)
        self._progress_label.configure(text="Parsing project files...")
        self._progress_frame.pack(fill="x", pady=(10, 10))

        self._analysis_thread = threading.Thread(
            target=self._run_analysis, args=(project_path, enabled), daemon=True,
        )
        self._analysis_thread.start()

    def _run_analysis(self, project_path: str, enabled_checks: list[str]) -> None:
        try:
            self.after(0, self._update_progress, "Parsing project files...", 0.0)
            project = load_project(project_path)

            file_count = len(project.files)
            self.after(0, self._update_progress, f"Parsed {file_count} .rpy files.", 0.1)

            total_checks = len(enabled_checks)
            findings: list[Finding] = []

            for idx, check_name in enumerate(enabled_checks):
                if self._cancel_event.is_set():
                    logger.info("Analysis cancelled by user")
                    self.after(0, self._analysis_cancelled)
                    return
                fraction = 0.1 + 0.85 * (idx / total_checks)
                self.after(0, self._update_progress, f"Running check: {check_name}...", fraction)
                check_fn = ALL_CHECKS[check_name]
                findings.extend(check_fn(project))

            if self._cancel_event.is_set():
                logger.info("Analysis cancelled by user")
                self.after(0, self._analysis_cancelled)
                return

            findings.sort(key=lambda f: f.severity)

            logger.info("Analysis complete: %d findings from %d checks", len(findings), total_checks)
            self.after(0, self._update_progress, "Analysis complete.", 1.0)
            self.after(100, self._analysis_complete, findings, project_path)

        except Exception as exc:
            logger.exception("Analysis failed")
            self.after(0, self._analysis_failed, str(exc))

    # -----------------------------------------------------------------------
    # GUI callbacks
    # -----------------------------------------------------------------------

    def _update_progress(self, text: str, fraction: float) -> None:
        self._progress_label.configure(text=text)
        self._progress_bar.set(fraction)
        self._status_var.set(text)

    def _analysis_complete(self, findings: list[Finding], project_path: str) -> None:
        self._findings = findings
        self._project_path = project_path

        self._progress_frame.pack_forget()

        self._analyze_btn.configure(state="normal")
        self._export_btn.configure(state="normal")

        # Summary
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
        self._summary_label.pack(fill="x", padx=5, pady=(6, 2))
        self._results_box.pack(fill="both", expand=True, pady=(4, 4))
        self._export_frame.pack(fill="x", pady=(2, 2))

        # Populate text widget
        self._populate_results(findings)

        if total == 0:
            self._status_var.set("Analysis complete — no issues found!")
        else:
            self._status_var.set(f"Analysis complete — {total} finding(s).")

    def _request_cancel(self) -> None:
        self._cancel_event.set()
        self._cancel_btn.configure(state="disabled")
        self._progress_label.configure(text="Cancelling...")

    def _analysis_cancelled(self) -> None:
        self._progress_frame.pack_forget()
        self._analyze_btn.configure(state="normal")
        self._status_var.set("Analysis cancelled.")

    def _analysis_failed(self, error_msg: str) -> None:
        self._progress_frame.pack_forget()
        self._analyze_btn.configure(state="normal")
        self._status_var.set(f"Error: {error_msg}")

    # -----------------------------------------------------------------------
    # Result display (single text widget — fast)
    # -----------------------------------------------------------------------

    def _populate_results(self, findings: list[Finding]) -> None:
        """Write all findings into the textbox using tags for colour."""
        self._results_box.configure(state="normal")
        self._results_box.delete("1.0", "end")
        inner: tk.Text = self._results_box._textbox

        if not findings:
            inner.insert("end", "No issues found — your project looks clean!\n")
            self._results_box.configure(state="disabled")
            return

        sev_tag_map = {
            Severity.CRITICAL: "severity_critical",
            Severity.HIGH: "severity_high",
            Severity.MEDIUM: "severity_medium",
            Severity.LOW: "severity_low",
            Severity.STYLE: "severity_style",
        }

        for idx, finding in enumerate(findings):
            sev = finding.severity
            tag = sev_tag_map[sev]

            # Severity badge + index
            inner.insert("end", f"[{sev.name}]", tag)
            inner.insert("end", f"  #{idx + 1}  ", "location")
            inner.insert("end", f"{finding.title}\n", "title")

            # Location
            inner.insert("end", f"  {finding.file}:{finding.line}\n", "location")

            # Description
            desc = finding.description
            if len(desc) > 300:
                desc = desc[:297] + "..."
            inner.insert("end", f"  {desc}\n")

            # Suggestion
            if finding.suggestion:
                sugg = finding.suggestion
                if len(sugg) > 300:
                    sugg = sugg[:297] + "..."
                inner.insert("end", f"  → {sugg}\n", "suggestion")

            # Separator
            inner.insert("end", "  " + "─" * 80 + "\n", "separator")

        self._results_box.configure(state="disabled")

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

        self._cancel_event.clear()
        self._status_var.set("Generating PDF report...")
        self._export_btn.configure(state="disabled")
        self._analyze_btn.configure(state="disabled")

        # Run PDF generation in a background thread to avoid freezing
        threading.Thread(
            target=self._run_pdf_export,
            args=(output_path,),
            daemon=True,
        ).start()

    def _run_pdf_export(self, output_path: str) -> None:
        try:
            project_path = getattr(self, "_project_path", "")
            game_name = Path(project_path).name if project_path else "Ren'Py Project"
            generate_pdf(
                findings=self._findings, output_path=output_path,
                game_name=game_name, game_path=project_path,
            )
            logger.info("PDF exported to %s", output_path)
            self.after(0, self._pdf_export_done, output_path, None)
        except Exception as exc:
            logger.exception("PDF export failed")
            self.after(0, self._pdf_export_done, output_path, str(exc))

    def _pdf_export_done(self, output_path: str, error: str | None) -> None:
        self._export_btn.configure(state="normal")
        self._analyze_btn.configure(state="normal")
        if error:
            self._status_var.set(f"PDF export failed: {error}")
        else:
            self._status_var.set(f"PDF saved to {output_path}")

    # -----------------------------------------------------------------------
    # Clean shutdown
    # -----------------------------------------------------------------------

    def destroy(self) -> None:
        """Override destroy to ensure clean exit without 'Not Responding'."""
        # Force-kill any background threads by just exiting
        import os
        os._exit(0)


def main() -> None:
    """Entry point for the GUI application."""
    setup_logging()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = RenpyAnalyzerApp()
    app.mainloop()
