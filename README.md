# EVC GUI v26.0.2

## Purpose
A maintainable PySide6 foundation for validating EVC communication and progressively replacing/augmenting the original LabVIEW GUI. Supported product selections are Quantum, Tykon, Triton, and Chronos.

## Roadmap
- Phase 1: GUI and serial communication validation.
- Phase 2: Real-time `pdat1` + `psum1` acquisition with Power Scope charting (implemented).
- Phase 3: Smith Chart.
- Phase 4: Future extensibility.

## State machine
`INITIALIZATION -> IDLE -> SCAN_EQUIPMENT -> CHECK_CONNECTION -> GETTING_START -> RUN -> SAVE_DATA`; contour download adds `DOWNLOADING_CONTOUR` as a transient busy state. Errors route to `ERROR`, while shutdown routes through `CLEANUP -> EXIT`.

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
1. Click **Start / Connect**. The app automatically:
   - Scans all available COM ports in parallel
   - Detects connected EVC devices and their information
   - Shows a device selection dialog with product name, serial number, firmware, and baud rate
   - User selects the device to connect to
2. Alternatively:
   - Click **Refresh Ports** to manually list available ports and select port/baud
   - Click **Start / Connect** to connect (falls back to baud rate scanning if needed)
3. Once connected:
   - Click **Run**. During `SCAN_EQUIPMENT`, the GUI sends `ver`, `sn`, issues `baud 7` to set **230400**, reconnects at **230400**, validates with `ver`, then enters continuous `pdat1` + `psum1` polling.
4. Open **Power Scope** to select traces, choose the latest **10 sec** or **60 sec** time window, and view current values.
5. If no real EVC data is available, enable **Demo Mode (Phase 2/3)** before Run to generate synthetic `pdat1`/`psum1` values and Smith Chart impedance demo patterns (VSWR=5 circle, spiral, linear, random).
6. During run, raw Phase 2 CSV files are written in `logs/` and rotated every 3 hours:
   - `<UnitSN>Tykon_GUI_<YYYYMMDD>_<HHMM>_raw.csv`
   - CSV `timestamp` values are written as `YYYY-MM-DD HH:MM:SS.mmm` (Excel-friendly with milliseconds)
7. Click **Probe** only when idle to send CR/LF for command-path verification.
8. Check `logs/` and `logs/python_fault.log` for troubleshooting.

## Auto-Detection Feature

The app now includes **intelligent COM port auto-detection**:
- Automatically discovers and identifies all connected EVC devices
- Displays device information in a selection dialog (product, serial number, firmware, detected baud rate)
- No manual port/baud selection required in most cases
- Supports multiple connected devices - user selects which to connect to
- Falls back to manual selection if needed

See **AUTO_DETECTION_FEATURE.md** for complete details and configuration options.

## Branding assets
Use `ASM-logo-small.gif` for splash branding and `smithchart.ico` for title bar/taskbar icon. The code resolves assets from `assets/` first, then from the runtime root folder.

## Build a single EXE
With the virtual environment active and approved assets present:

`pyinstaller --noconfirm --clean --onefile --windowed --name "EVC_GUI_v26.0.2" --icon "smithchart.ico" --add-data "ASM-logo-small.gif;." main.py`

The output will be `dist\EVC_GUI_v26.0.2.exe`. PyInstaller one-file extraction means external writable logs are created beside the EXE when permissions allow. For controlled production deployment, use a writable deployment folder.

## Project layout
- `version.py`: version and history source of truth
- `evc_gui/state_machine.py`: transition rules
- `evc_gui/services/serial_service.py`: hardware boundary
- `evc_gui/services/port_scanner.py`: COM port auto-detection engine
- `evc_gui/ui/main_window.py`: primary application window
- `evc_gui/ui/device_selection_dialog.py`: device selection UI
- `evc_gui/ui/`: splash and chart widgets
- `evc_gui/logging_config.py`: rotating logs and fault capture
- `RELEASE_CHECKLIST_v26.0.2.md`: repeatable release procedure
- `AUTO_DETECTION_FEATURE.md`: detailed auto-detection documentation

## Notes
The original PDFs are design references, not runtime dependencies. Device-specific commands, response parsing, tlog timing, and product-specific protocol adapters should be added behind the service boundary instead of directly inside Qt widgets.
