# Changelog

All notable changes to this project are documented in this file.

## [1.0.2] - 2026-09-27

### Added
- Phase 2 real-time data pipeline: continuous `pdat1` + `psum1` acquisition, parsing to measured sample model, ring buffer, and chart refresh timer separation.
- Power Scope chart widget with selectable traces, 10s/60s window controls, current-value panel, and multi-axis plotting for power/cap/Vpp/DcBias/Iout.
- CSV logging strategy for Phase 2 raw and parsed data with metadata fields (`timestamp`, `product`, `serial_number`, `firmware`, `session_id`).
- Demo Mode for Phase 2 to generate synthetic values when real EVC data is unavailable.

### Fixed
- Restored Power Scope curve rendering by correcting `QChart` series/axis binding order.

### Changed
- README and release checklist references updated for `v1.0.2`.

## [1.0.1] - 2026-09-26

### Added
- Splash now loads `ASM-logo-small.gif` with fallback search in runtime root.
- App and main window now use `smithchart.ico` for title bar/taskbar icon.
- `ver` and `sn` command handling in scan flow to detect product type and unit serial number.
- UI fields for detected product type and detected unit serial number.
- SN-based log file naming (`logs/evc_gui_<UnitS_N>.log`).

### Changed
- Default baud rate updated to `57600`.
- Start/Connect and Run control flow tightened to keep controls in a safe disabled/enabled state.
- Release checklist updated to `RELEASE_CHECKLIST_v1.0.1.md`.
- Build naming/docs updated from `v1.0.0` to `v1.0.1`.

## [1.0.0] - 2026-09-26

### Added
- Phase 1 foundation: PySide6 GUI, state machine, serial validation path, splash screen, logging, and release assets.
