# Changelog

All notable changes to this project are documented in this file.

## [26.0.0] - 2026-09-28

### Added
- Quantum dual-frequency support for runtime parsing: `pdat1` and `psum1` now capture both HF and LF halves from the same response line.
- Power Scope HF/LF selector for Quantum to switch chart/value display between HF and LF data.
- Smith Chart dual-impedance plotting for Quantum with HF marker in red and LF marker in blue.
- Dual-band contour download for Quantum using both `zpar show hf ...` and `zpar show lf ...`, then overlaying both on the same Smith Chart.
- `build_exe.ps1` helper script to build one-file Windows EXE with project-standard PyInstaller settings.

### Changed
- Product naming now distinguishes Chronos generations using SN prefix: `Chronos 1` (191-195) and `Chronos 2.0` (196+).
- Contour capacitor-grid mapping now applies Chronos generation rules (Chronos 1 uses `0..12/0..12`; Chronos 2.0 follows Tykon range).
- Start/Connect baud detection now uses stricter `ver` content validation and multi-baud scanning order for faster wrong-baud recovery.
- Smith contour cache/export now includes Quantum band context for HF/LF workflows.

### Fixed
- Chronos parsing compatibility for no-pipe `psum1` format.
- `zpar show` response handling robustness (prompt timing/content parsing), eliminating false empty-contour failures.

### Removed
- Parsed Phase 2 CSV output path; Phase 2 logging remains raw CSV only.

## [1.0.5] - 2026-09-28

### Added
- Automatic contour `zpar` pre-download after successful equipment scan to reduce user mis-operation before run.
- Clickable Power Scope Y-axis scaling dialog with user-settable Min/Max/Step.
- Smarter Start/Connect baud recovery with prioritized multi-baud scanning and stricter `ver` handshake validation.

### Changed
- Chronos product detection now labels units as `Chronos 1` (SN prefix 191-195) and `Chronos 2.0` (SN prefix >=196).
- Contour capacitor-grid mapping is now product-generation aware: Chronos 1 uses `0..12/0..12`, while Chronos 2.0 follows Tykon range.
- `ver` identity checks now require valid echo/content and reject prompt-only or garbled response payloads.

### Fixed
- Chronos `psum1` parsing for no-pipe format so run-time metrics and scope updates are stable.
- `zpar show` response handling for Chronos formatting and prompt timing, preventing false "No Z-parameters loaded" failures.

### Removed
- Parsed Phase 2 CSV output path; run logging is now raw CSV only to reduce memory/storage overhead.

## [1.0.4] - 2026-09-27

### Added
- Dual-baud connection validation on Start/Connect (57600 and 230400) with response-content checks to reject garbled `ver`/`sn` data.
- High-speed transition flow in scan stage: `baud 7` command, reconnect at 230400, and post-switch `ver` verification with settle/retry logic.
- Expanded raw Phase 2 CSV fields for `pdat1` and `psum1` tokenized columns.

### Changed
- `ver` and `sn` scan commands now use 500 ms timeout.
- Phase 2 polling command timeout reduced to 75 ms after entering run pipeline.
- Phase 2 log file naming updated to `<UnitSN>Tykon_GUI_<YYYYMMDD>_<HHMM>_{raw|parsed}.csv`.
- CSV timestamp format changed to `YYYY-MM-DD HH:MM:SS.mmm` for direct Excel recognition.
- CSV writers now rotate every 3 hours.

### Removed
- Raw CSV metadata columns `product`, `serial_number`, and `session_id` to reduce file size.

## [1.0.3] - 2026-09-27

### Added
- Cached contour database for Smith Chart boundary reference lines.
- Busy-state indicator for first-time contour download with a dedicated `DOWNLOADING_CONTOUR` machine state.
- One-time `zpar` contour download flow: subsequent contour toggles reuse cached data instead of re-downloading.

### Fixed
- Smith Chart contour now plots each boundary line as its own series to prevent multi-line polyline corruption.
- Contour download state no longer appears as `IDLE` while data is being fetched.
- Demo mode is blocked from contour download to avoid invalid data acquisition.

### Changed
- Contour sampling uses real capacitor index resolution instead of coarse/fine percentage approximation.

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
