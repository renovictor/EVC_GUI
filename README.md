# EVC GUI v1.0.0

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
1. Choose Quantum, Tykon, Triton, or Chronos.
2. Click **Refresh Ports**.
3. Choose the COM port and baud rate.
4. Click **Start / Connect** to validate that the port can be opened.
5. Click **Probe** to send CR/LF. Replace the probe bytes in `SerialService.probe()` with the approved EVC command after the command protocol is confirmed.
6. Click **Run** to validate the state flow. Phase 2 collection is deliberately disabled.
7. Check `logs/evc_gui.log` and `logs/python_fault.log` for troubleshooting.

## Branding assets
Place the approved corporate `ASM-logo-small.gif` and application `evc_gui.ico` in `assets/`. The code uses a text fallback if either is unavailable. Use an approved `.ico` containing 16, 24, 32, 48, 64, 128, and 256 pixel sizes for Windows title bar, taskbar, file icon, and EXE icon.

## Build a single EXE
With the virtual environment active and approved assets present:

`pyinstaller --noconfirm --clean --onefile --windowed --name "EVC_GUI_v1.0.0" --icon "assets\evc_gui.ico" --add-data "assets\ASM-logo-small.gif;assets" main.py`

The output will be `dist\EVC_GUI_v1.0.0.exe`. PyInstaller one-file extraction means external writable logs are created beside the EXE when permissions allow. For controlled production deployment, use a writable deployment folder.

## Project layout
- `version.py`: version and history source of truth
- `evc_gui/state_machine.py`: transition rules
- `evc_gui/services/serial_service.py`: hardware boundary
- `evc_gui/ui/`: splash and main window
- `evc_gui/logging_config.py`: rotating logs and fault capture
- `RELEASE_CHECKLIST_v1.0.0.md`: repeatable release procedure

## Notes
The original PDFs are design references, not runtime dependencies. Device-specific commands, response parsing, tlog timing, and product-specific protocol adapters should be added behind the service boundary instead of directly inside Qt widgets.
