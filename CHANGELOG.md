# Changelog

All notable changes to this project are documented in this file.

## [26.0.7] - 2026-09-30

### Added
- New **Log1 / Log2 / Log3** acquisition controls:
  - **Log1**: `pdat1 + psum1`
  - **Log2**: `tlog 1`
  - **Log3**: `tlog rt` streaming mode
- Runtime **RUN Profile** tuning support (Baseline / Aggressive / Max Throughput) for A/B throughput testing.
- In-app 10-loop sample-rate benchmark reporting for live/final performance comparison.
- Hover tooltips for Log1/Log2/Log3 buttons to explain acquisition behavior to users.
- Benchmark record document `SAMPLE_RATE_BENCHMARK_2026-09-30.md`.

### Changed
- `tlog` parser handling expanded for cross-device format variation (Quantum HF/LF paired rows, Triton/Tykon/Chronos variants).
- Chronos family now falls back from Log3 (`tlog rt`) to Log2 (`tlog 1`) automatically because `tlog rt` is unsupported on sampled Chronos units.

### Fixed
- Raw log filename convention restored to use detected product type (`<SN><Product>_GUI_...`) instead of hardcoded `Tykon`.

## [26.0.6] - 2026-09-30

### Changed
- Start/Connect now enforces the expected baud sequence: query `ver`/`sn` at **57600**, then switch to **230400** for high-speed operation.
- Auto contour (`zpar`) flow now explicitly verifies high-speed serial before download to preserve fast transfer behavior.

### Fixed
- Prevented false baud-switch success when EVC returns `Invalid Command`; baud transitions now require real device-side confirmation.
- App exit now performs a robust low-speed restore path, including low-speed command fallback (`baud 5` then `baud 6`) and reconnect/`ver` confirmation at **57600**.

## [26.0.5] - 2026-09-30

### Changed
- Optimized contour `zpar` download path from about **130s** to about **13s** by using faster command-read completion logic.
- Added a live **USB State** field under system state to show whether serial USB is connected or disconnected.

### Fixed
- Backup/Advanced Diagnostic `back` download now treats `Printed from : EVC` as end-of-response so the app can finish and save immediately after transfer completion.
- Backup/Advanced Diagnostic now detect `Invalid Command` from older EVC firmware and report backup as unsupported instead of attempting to save as a successful download.
- `tlog`/`back` diagnostic commands now use CR-only (`\r`) command termination to avoid sending an extra keystroke that can prematurely stop long tlog downloads.
- Result text box content is now saved once on app exit to `snTykon_GUI_<date>_<time>_result.txt`.
- Demo-mode raw logs now record non-zero, continuously varying fake measurements from run start (Pfwd/Pref/Vpp/C1/C2/Rs/Xs/etc.) instead of staying at zero for short runs.
- `tlog` reliability improved for long logs: timeout increased to 300s and missing `Printed from : EVC` end-marker now reports an incomplete download instead of false success.
- When `tlog` times out before footer but has data, the app now saves a `_tlog_partial.txt` file and reports partial-download status instead of losing captured output.
- `tlog` now supports auto multi-part collection (retries incomplete chunks up to a capped part count) and merges captured parts into one output.
- USB state display now includes active baud rate (for example `Connected (COM82 @ 230400)`).
- Diagnostic/log filename prefix now uses detected product type (`<SN><Product>_GUI_...`) instead of hardcoded `Tykon` (e.g., Quantum/Triton names are preserved).

## [26.0.2] - 2026-09-28

### Added
- New **Troubleshoot** tab with a **Diagnostic** button and read-only result display box.
- Diagnostic flow that runs `stat`, detects `Active Faults`, and lists fault code + explanation for users.

### Changed
- Renamed the previous `Future` tab to `Troubleshoot`.

### Fixed
- Fault parsing now extracts active fault entries from `stat` output reliably until section end/prompt.
- Fault code presentation includes mapped descriptions for current Tykon cases (`25`, `43`).

## [26.0.1] - 2026-09-28

### Added
- Bright red progress bar (40px height, thick styling) for contour download visibility.
- Progress bar shown during long-running contour download operations with real-time updates.
- Visual feedback for download progress (0-100% fill based on Z-parameter query count).

### Changed
- Progress bar updates throttled to every 10 queries to prevent serial communication blocking.
- Progress updates now occur after successful Z-parameter validation to ensure serial integrity.
- Progress bar automatically hidden when download completes or fails.

### Fixed
- Progress bar no longer interferes with serial communication during contour download.
- Z-parameter queries now complete successfully without being interrupted by UI updates.

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
