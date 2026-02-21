# Ren'Py Analyzer

A desktop GUI tool that scans [Ren'Py](https://www.renpy.org/) visual novel projects for bugs and generates styled PDF reports.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## What It Does

Ren'Py Analyzer statically analyzes `.rpy` script files and detects common bugs that are easy to miss during development but can cause crashes, broken logic, or cross-platform failures.

### Checks

| Check | Severity | What It Catches |
|-------|----------|-----------------|
| **Labels** | CRITICAL/MED | Missing jump/call targets, duplicate labels, dynamic jump/call expression warnings |
| **Logic** | CRITICAL/STYLE | Operator precedence bugs (`if A or B == True`), explicit bool comparisons |
| **Variables** | CRITICAL/HIGH/MED/LOW | Define-mutation (save/load bug), duplicate defaults, persistent-define misuse, builtin shadowing, case mismatches, undeclared variables, unused defaults |
| **Menus** | HIGH/MED | Empty choices, fallthrough paths, single-option menus |
| **Assets** | HIGH/MED | Missing scene images, movie path casing, audio file path validation (sound/voice/music/audio), image subdirectory auto-detection |
| **Characters** | HIGH/LOW | Undefined speakers, unused character definitions |
| **Flow** | HIGH | Unreachable code after jump/return statements |

### Example Findings

```
[CRITICAL] scripts/ch15_script.rpy:2080 — Operator precedence bug: 'SamSex2 or SamSex3 == True'
  -> Python parses this as: SamSex2 or (SamSex3 == True)

[CRITICAL] scripts/variables.rpy:12 — Defined variable 'points' mutated
  -> Variable declared with 'define' but modified later. Changes lost on save/load.

[HIGH] scripts/variables.rpy:266 — Case mismatch: 'marysex4_Slow_3' vs family 'marysex4_slow_1'
  -> Ren'Py is case-sensitive. Inconsistent casing can cause undefined variable errors.

[MEDIUM] animations.rpy:45 — Directory case mismatch in path 'images/animations/ch21/...'
  -> Actual directory is 'images/Animations/'. Works on Windows, fails on Linux/macOS.
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
- **reportlab** — PDF report generation
- **Pillow** — Image support (CustomTkinter dependency)
- **click** — CLI interface

## Usage

### GUI Mode (default)

```bash
python -m renpy_analyzer
```

1. Browse to your Ren'Py project folder (or the `game/` subfolder — it auto-detects)
2. Optionally set an SDK path for more accurate parsing
3. Toggle which checks to run
4. Click **Analyze**
5. Review color-coded results
6. Click **Export PDF** to generate a styled report

### CLI Mode

```bash
# Basic analysis
python -m renpy_analyzer --cli /path/to/game

# With specific checks and PDF output
python -m renpy_analyzer --cli /path/to/game --checks Labels,Variables --output report.pdf

# JSON output for tooling
python -m renpy_analyzer --cli /path/to/game --format json

# Use SDK parser for more accurate results
python -m renpy_analyzer --cli /path/to/game --sdk-path /path/to/renpy-sdk
```

Exit codes: `0` = no findings, `1` = findings found, `2` = error.

### SDK Parser (Optional)

By default, Ren'Py Analyzer uses a regex-based parser. For more accurate results, you can point it at a Ren'Py SDK installation, which uses the SDK's own parser via a subprocess bridge:

- **GUI**: Set the "SDK Path" field to your Ren'Py SDK directory
- **CLI**: Pass `--sdk-path /path/to/renpy-sdk`

The regex parser remains the zero-dependency fallback.

## PDF Report

The generated PDF uses a midnight dark theme and includes:

- Styled title page with project name, date, and finding statistics
- Clickable table of contents with dotted leaders
- Bookmark sidebar for quick navigation
- Color-coded severity badges (vibrant against dark background)
- Tiered display: full cards for CRITICAL/HIGH, compact cards for MEDIUM, table rows for LOW/STYLE
- Identical findings grouped to reduce report noise
- Summary table with counts by category and severity

## Project Structure

```
src/renpy_analyzer/
├── app.py              # GUI (CustomTkinter, dark mode, threaded analysis)
├── analyzer.py         # Core analysis engine (shared by GUI and CLI)
├── cli.py              # CLI interface (click)
├── parser.py           # .rpy file parser -> structured elements
├── project.py          # Project loader: finds .rpy files, builds model
├── models.py           # Dataclasses for all parsed elements + findings
├── log.py              # Structured logging setup
├── bridge_worker.py    # SDK parser worker (runs under SDK Python)
├── sdk_bridge.py       # Host-side subprocess bridge for SDK parser
├── checks/
│   ├── labels.py       # Missing label targets, duplicate labels, dynamic jumps
│   ├── variables.py    # Undeclared, unused, case mismatches, define-mutation, builtins
│   ├── logic.py        # Operator precedence bugs, explicit bool comparison
│   ├── menus.py        # Empty choices, fallthroughs, single-option
│   ├── assets.py       # Missing images, audio file paths, animation path casing
│   ├── characters.py   # Undefined speakers, unused character defs
│   └── flow.py         # Unreachable code after jump/return
└── report/
    ├── finding.py       # Finding dataclass with severity levels
    └── pdf.py           # Styled PDF generator (ReportLab, midnight theme)
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all unit tests (<1s)
PYTHONPATH=src python3 -m pytest tests/ --ignore=tests/test_integration.py -q

# Run a specific test file
PYTHONPATH=src python3 -m pytest tests/test_parser.py -v

# Run integration tests (~6 min, requires real game project)
PYTHONPATH=src python3 -m pytest tests/test_integration.py -v
```

### Test Suite

- **188 unit tests** covering parser, models, project loader, analyzer, CLI, PDF, logging, SDK bridge, and all 7 check modules
- **5 integration tests** against a real Ren'Py project

### Building Windows Executable

```bash
# Using PyInstaller with the included spec file
python -m PyInstaller renpy_analyzer.spec --clean --noconfirm
```

Output: `dist/RenpyAnalyzer.exe` (~34MB single-file executable).

## How It Works

```
.rpy files -> Parser -> Project Model -> Checks -> Findings -> Report (GUI / PDF)
```

1. **Project loader** discovers all `.rpy` files recursively in the `game/` directory
2. **Parser** reads each file using regex patterns (or SDK parser if configured) to extract labels, jumps, calls, variables, menus, scenes, characters, images, music references, conditions, and dialogue
3. **Check modules** receive the full project model and independently analyze it for issues
4. **Findings** are collected with severity, file location, message, and explanation
5. **Report** displays findings in the GUI results list and/or exports to a styled PDF

### Ren'Py-Specific Features

- Handles indented labels (nested inside `if`/`menu` blocks)
- Scans `game/images/` for auto-discovered images with subdirectory support
- Pattern-based case mismatch detection for numbered variable families (e.g., `varName_1` vs `varname_2`)
- Understands `default`, `define`, `$` assignments, augmented assignments (`+=`)
- Parses menu blocks with dynamic indent detection (2-space, 4-space, tabs)
- Parses all audio channels: `play music/sound/voice/audio`, `queue`, standalone `voice`, `stop`
- Multi-word image names in `scene`/`show` statements
- Dynamic `jump expression` / `call expression` detection
- Filters Ren'Py built-in images (`black`, `white`) and keywords (`narrator`, `extend`) from checks

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by the [Ren'Py](https://www.renpy.org/) project or Tom Rothamel. "Ren'Py" is a registered trademark of Tom Rothamel. This tool uses the name solely to describe its purpose: analyzing Ren'Py project files.

The optional SDK parser feature invokes the user's own locally-installed Ren'Py SDK via subprocess. No Ren'Py code is bundled or redistributed with this tool.

## License

MIT — see [LICENSE](LICENSE) for details.
