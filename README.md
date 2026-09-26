# EVC GUI v1.0.2

## Purpose
A maintainable PySide6 foundation for validating EVC communication and progressively replacing/augmenting the original LabVIEW GUI. Supported product selections are Quantum, Tykon, Triton, and Chronos.

## Roadmap
- Phase 1: GUI and serial communication validation.
- Phase 2: Real-time `pdat1` + `psum1` acquisition with Power Scope charting (implemented).
- Phase 3: Smith Chart.
- Phase 4: Future extensibility.

## State machine
`INITIALIZATION -> IDLE -> SCAN_EQUIPMENT -> CHECK_CONNECTION -> GETTING_START -> RUN -> SAVE_DATA`; errors route to `ERROR`, while shutdown routes through `CLEANUP -> EXIT`. Phase 1 intentionally implements only safe communication validation and GUI placeholders.

## Install
1. Install 64-bit Python 3.11 or 3.12.
2. Open PowerShell in this folder.
3. Create an environment: `py -m venv .venv`
4. Activate it: `.\.venv\Scripts\Activate.ps1`
5. Upgrade packaging tools: `python -m pip install --upgrade pip wheel`
6. Install all packages: `pip install -r requirements.txt`
7. For Phase 1 only, use: `pip install -r requirements-minimal.txt`

## Run
`python main.py`

At startup, a borderless 5-second splash screen immediately appears. The loader checks/imports modules on a background QThread. Optional modules are silently tolerated when missing. Required serial support is supplied by PySerial.

## Operation
1. Click **Refresh Ports**.
2. Choose the COM port and baud rate (default is **57600**).
3. Click **Start / Connect** to validate that the port can be opened.
4. Click **Run**. During `SCAN_EQUIPMENT`, the GUI sends `ver`, `sn`, then enters continuous `pdat1` + `psum1` polling.
5. Open **Power Scope** to select traces, choose the latest **10 sec** or **60 sec** time window, and view current values.
6. If no real EVC data is available, enable **Demo Mode (Phase 2)** before Run to generate synthetic `pdat1`/`psum1` values for chart validation.
7. During run, parsed/raw Phase 2 CSV files are written in `logs/`:
   - `phase2_raw_<UnitS/N>_<timestamp>.csv`
   - `phase2_parsed_<UnitS/N>_<timestamp>.csv`
8. Click **Probe** only when idle to send CR/LF for command-path verification.
9. Check `logs/` and `logs/python_fault.log` for troubleshooting.

## Branding assets
Use `ASM-logo-small.gif` for splash branding and `smithchart.ico` for title bar/taskbar icon. The code resolves assets from `assets/` first, then from the runtime root folder.

## Build a single EXE
With the virtual environment active and approved assets present:

`pyinstaller --noconfirm --clean --onefile --windowed --name "EVC_GUI_v1.0.2" --icon "smithchart.ico" --add-data "ASM-logo-small.gif;." main.py`

The output will be `dist\EVC_GUI_v1.0.2.exe`. PyInstaller one-file extraction means external writable logs are created beside the EXE when permissions allow. For controlled production deployment, use a writable deployment folder.

## Project layout
- `version.py`: version and history source of truth
- `evc_gui/state_machine.py`: transition rules
- `evc_gui/services/serial_service.py`: hardware boundary
- `evc_gui/ui/`: splash and main window
- `evc_gui/logging_config.py`: rotating logs and fault capture
- `RELEASE_CHECKLIST_v1.0.2.md`: repeatable release procedure

## Notes
The original PDFs are design references, not runtime dependencies. Device-specific commands, response parsing, tlog timing, and product-specific protocol adapters should be added behind the service boundary instead of directly inside Qt widgets.
