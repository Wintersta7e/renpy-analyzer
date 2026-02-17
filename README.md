# Ren'Py Analyzer

A desktop GUI tool that scans [Ren'Py](https://www.renpy.org/) visual novel projects for bugs and generates styled PDF reports.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## What It Does

Ren'Py Analyzer statically analyzes `.rpy` script files and detects common bugs that are easy to miss during development but can cause crashes, broken logic, or cross-platform failures.

### Checks

| Check | Severity | What It Catches |
|-------|----------|-----------------|
| **Labels** | CRITICAL | Missing jump/call targets, duplicate label definitions |
| **Logic** | CRITICAL | Operator precedence bugs (`if A or B == True`) |
| **Variables** | HIGH/MED/LOW | Case mismatches, undeclared variables, unused defaults |
| **Menus** | HIGH/MED | Empty choices, fallthrough paths, single-option menus |
| **Assets** | HIGH/MED | Missing scene images, animation path casing issues (Linux/macOS) |
| **Characters** | HIGH/LOW | Undefined speakers, unused character definitions |

### Example Findings

```
[CRITICAL] scripts/ch15_script.rpy:2080 — Operator precedence bug: 'SamSex2 or SamSex3 == True'
  → Python parses this as: SamSex2 or (SamSex3 == True)

[HIGH] scripts/variables.rpy:266 — Case mismatch: 'marysex4_Slow_3' vs family 'marysex4_slow_1'
  → Ren'Py is case-sensitive. Inconsistent casing can cause undefined variable errors.

[MEDIUM] animations.rpy:45 — Directory case mismatch in path 'images/animations/ch21/...'
  → Actual directory is 'images/Animations/'. Works on Windows, fails on Linux/macOS.
```

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/renpy-analyzer.git
cd renpy-analyzer

# Install in development mode
pip install -e ".[dev]"
```

### Dependencies

- **customtkinter** — GUI framework (dark mode)
- **PyMuPDF** — PDF report generation
- **Pillow** — Image support (CustomTkinter dependency)

## Usage

### GUI Mode (default)

```bash
python -m renpy_analyzer
```

1. Browse to your Ren'Py project folder (or the `game/` subfolder — it auto-detects)
2. Toggle which checks to run
3. Click **Analyze**
4. Review color-coded results
5. Click **Export PDF** to generate a styled report

### What the GUI Looks Like

- Dark mode interface
- Check toggles in a 2x3 grid
- Progress bar during analysis
- Color-coded results list (red = critical, orange = high, yellow = medium, etc.)
- One-click PDF export

## PDF Report

The generated PDF includes:

- Styled title page with project name and date
- Clickable table of contents with dotted leaders
- Bookmark sidebar for quick navigation
- Color-coded severity badges per finding
- Code context with monospace formatting
- Summary table with counts by category and severity

## Project Structure

```
src/renpy_analyzer/
├── app.py              # GUI (CustomTkinter, dark mode, threaded analysis)
├── parser.py           # .rpy file parser → structured elements
├── project.py          # Project loader: finds .rpy files, builds model
├── models.py           # Dataclasses for all parsed elements + findings
├── checks/
│   ├── labels.py       # Missing label targets, duplicate labels
│   ├── variables.py    # Undeclared, unused, case mismatches
│   ├── logic.py        # Operator precedence bugs
│   ├── menus.py        # Empty choices, fallthroughs, single-option
│   ├── assets.py       # Missing images, animation path casing
│   └── characters.py   # Undefined speakers, unused character defs
└── report/
    ├── finding.py       # Finding dataclass with severity levels
    └── pdf.py           # Styled PDF generator (PyMuPDF)
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/ tests/

# Run a specific test
pytest tests/test_parser.py -v
```

### Test Suite

- **39 unit tests** covering parser, models, project loader, and all 6 check modules
- **5 integration tests** against a real Ren'Py project

## How It Works

```
.rpy files → Parser → Project Model → Checks → Findings → Report (GUI / PDF)
```

1. **Project loader** discovers all `.rpy` files recursively in the `game/` directory
2. **Parser** reads each file line-by-line using regex patterns to extract labels, jumps, calls, variables, menus, scenes, characters, images, music references, conditions, and dialogue
3. **Check modules** receive the full project model and independently analyze it for issues
4. **Findings** are collected with severity, file location, message, and explanation
5. **Report** displays findings in the GUI results list and/or exports to a styled PDF

### Ren'Py-Specific Features

- Handles indented labels (nested inside `if`/`menu` blocks)
- Scans `game/images/` for auto-discovered images (Ren'Py registers files automatically)
- Pattern-based case mismatch detection for numbered variable families (e.g., `varName_1` vs `varname_2`)
- Understands `default`, `define`, `$` assignments, augmented assignments (`+=`)
- Parses menu blocks with choice conditions (`"Text" if flag:`)
- Filters Ren'Py built-in images (`black`, `white`) from scene checks

## License

MIT
