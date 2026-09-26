# EVC GUI v1.0.1

## Purpose
A maintainable PySide6 foundation for validating EVC communication and progressively replacing/augmenting the original LabVIEW GUI. Supported product selections are Quantum, Tykon, Triton, and Chronos.

## Roadmap
- Phase 1: GUI and serial communication validation, implemented in this release.
- Phase 2: Real-time tlog acquisition and Pfwd, Pref, C1, C2, Vpp, and DC Bias charts.
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
4. Click **Run**. During `SCAN_EQUIPMENT`, the GUI sends `ver` and displays the detected product type from the response.
5. After `ver`, the GUI sends `sn`, displays `Unit S/N`, and switches logging to `logs/evc_gui_<UnitS/N>.log`.
6. Click **Probe** to send CR/LF for basic command-path verification.
7. Check `logs/` and `logs/python_fault.log` for troubleshooting.

## Branding assets
Use `ASM-logo-small.gif` for splash branding and `smithchart.ico` for title bar/taskbar icon. The code resolves assets from `assets/` first, then from the runtime root folder.

## Build a single EXE
With the virtual environment active and approved assets present:

`pyinstaller --noconfirm --clean --onefile --windowed --name "EVC_GUI_v1.0.1" --icon "smithchart.ico" --add-data "ASM-logo-small.gif;." main.py`

The output will be `dist\EVC_GUI_v1.0.1.exe`. PyInstaller one-file extraction means external writable logs are created beside the EXE when permissions allow. For controlled production deployment, use a writable deployment folder.

## Project layout
- `version.py`: version and history source of truth
- `evc_gui/state_machine.py`: transition rules
- `evc_gui/services/serial_service.py`: hardware boundary
- `evc_gui/ui/`: splash and main window
- `evc_gui/logging_config.py`: rotating logs and fault capture
- `RELEASE_CHECKLIST_v1.0.1.md`: repeatable release procedure

## Notes
The original PDFs are design references, not runtime dependencies. Device-specific commands, response parsing, tlog timing, and product-specific protocol adapters should be added behind the service boundary instead of directly inside Qt widgets.
