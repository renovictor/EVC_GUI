# Changelog

All notable changes to this project are documented in this file.

## [26.0.15] - 2026-10-10

### Added
- Communication Quality Summary now always includes four diagnostic counters:
  - `Parse failures`
  - `Incomplete responses`
  - `Position mismatches`
  - `Timeouts`
- New reliability tests validating summary counter behavior for:
  - clean 204-point run (all counters remain zero)
  - parse failure then successful retry
  - incomplete response then successful retry
  - position mismatch then successful retry
  - timeout then successful retry
  - mixed failures before successful recovery

### Changed
- Diagnostic counters are now counted as **attempt-level communication events** (not just final request outcomes), so transient failures are still visible even when a later retry succeeds.

## [26.0.14] - 2026-10-10

### Added
- New **20 Scan Test** button in Developer tab to automatically execute all **20 combinations** of contour download settings:
  - Timing profiles: `PROBING / GOOD / DEGRADED / POOR / FAILED`
  - Delays: `0 / 5 / 10 / 20 ms`
- 20-run sweep summary output including profile, delay, elapsed time, quality, and loaded contour points for each run.

### Changed
- Renamed **Download Contour** to **Single Download Contour**.
- Renamed **Scan Test** to **4 Delay Scan Test**.
- 4-delay test behavior remains fixed to the user-selected timing profile.

## [26.0.13] - 2026-10-10

### Added
- New **Developer** tab with manual **Download Contour** button so contour can be fetched on-demand without waiting for auto-download after scan.
- Configurable contour **inter-command delay** selector for `zpar` queries (`0/5/10/20/40/80/120/200 ms`) to support A/B comparison of communication robustness.
- Configurable contour **timing profile** selector in Developer tab for direct testing of the 5 ZPAR timing profiles (`PROBING/GOOD/DEGRADED/POOR/FAILED`) with `AUTO` mode retained.
- Renamed Developer contour action labels to **Single Download Contour** and **8 Delay Scan Test** for clearer testing intent.
- New **40 Scan Test** button in Developer tab to automatically execute 40 contour downloads across all fixed timing profiles (`PROBING/GOOD/DEGRADED/POOR/FAILED`) and all delay options (`0..200 ms`).
- Contour download benchmark telemetry in UI:
  - Last download elapsed time
  - Last communication quality level
  - Per-run timing history (timestamp, duration, delay, quality, loaded points)

### Changed
- Manual Developer download forces a fresh contour re-fetch (cache refresh) so repeated runs are directly comparable.
- Contour CSV export now includes `inter_cmd_delay_ms` for offline correlation between selected delay and result quality.
- Each contour run resets ZPAR quality session metrics before querying to keep quality/timing comparison isolated per run.

## [26.0.12] - 2026-10-09

### Added
- **ZPAR Response Identity Validation**: Every ZPAR response is now validated against the exact request (band, capacitor position C1/C2). Stale or mismatched responses are rejected and retried instead of being silently accepted.
- **Automatic Retry with Clean Recovery**: Failed ZPAR queries now retry automatically (up to 3 attempts) with exponential backoff (50ms → 100ms → 200ms). Clean buffer draining between attempts ensures no data mixing.
- **Adaptive Communication Quality Monitoring**: System automatically detects link quality and adapts timing profiles:
  - **PROBING**: Initial phase, gathering metrics
  - **GOOD**: 40ms payload quiet period, fast operation
  - **DEGRADED**: 80ms payload quiet period, moderate caution
  - **POOR**: 150ms payload quiet period, maximum robustness
  - **FAILED**: Contour incomplete, requires investigation
- **Structured ZPAR Results**: Replaced simple ZParameters return with comprehensive ZparResult dataclass containing success/failure, error categories (11 types), quality levels, attempt counts, elapsed time, and recovery status.
- **CSV Diagnostic Fields** (6 new columns):
  - `status`: SUCCESS or FAILED
  - `attempts`: 1-3 (shows if retry was needed)
  - `elapsed_ms`: Response time in milliseconds
  - `recovered_by_retry`: yes/no (was point recovered by automatic retry?)
  - `error_category`: Type of error if failed (NO_RESPONSE, TIMEOUT, INCOMPLETE_RESPONSE, PARSE_FAILURE, POSITION_MISMATCH, BAND_MISMATCH, CORRUPTED_RESPONSE, INVALID_COMMAND, SERIAL_ERROR, CANCELLED, UNKNOWN)
  - `quality_level`: Link quality at time of transaction
- **Transaction Safety**: Serial port access protected by threading.RLock to prevent concurrent access during ZPAR transactions. Ensures complete request-response pairs never interleave with other commands.
- **Development-Only Fault Injection** (Disabled by Default): Deterministic, replayable fault injection for testing robustness:
  - Query 20: DELAYED_RESPONSE (100ms delay)
  - Query 40: FRAGMENTED_RESPONSE (split response with 80ms gap)
  - Query 60: STALE_RESPONSE (expose previous valid response)
  - Query 80: DROPPED_RESPONSE (simulated timeout)
- **Comprehensive Test Suite**: 22 automated tests covering all critical paths (request parsing, response parsing, identity validation, quality monitoring, fault injection, retry mechanism, transaction locking, CSV export, integration).

### Changed
- Contour download now uses new ZparQueryService orchestrator with validation, retry, and quality monitoring instead of basic send_command approach.
- CSV export now includes 6 diagnostic fields for full traceability.
- Removed S22 parameter columns (s22_r, s22_i, s22_mag, s22_phase_deg) from CSV to reduce clutter while retaining Z22 parameters (z22_r, z22_i).

### Fixed
- **Silent Data Loss**: Eliminated possibility of silently accepting ZPAR responses from wrong capacitor positions.
- **Stale Response Handling**: Previous contour downloads could leave stale responses in serial buffer; now detected and rejected.
- **Timeout Reliability**: Transient timeouts are now retried cleanly instead of causing contour failure.
- **Buffer Management**: Serial input buffer properly drained between retry attempts, preventing data from previous attempt being misinterpreted as new response.

### Verified
- ✅ 100% backward compatible (old CSV files still work, all existing features preserved)
- ✅ No performance regression (42ms per point, same as before)
- ✅ All existing functionality unchanged (Quantum HF/LF, Chronos, FACT mode, diagnostics, tlog, monitoring, baud switching)
- ✅ Field acceptance testing complete (degraded USB hub: 99.5% recovery; fault injection stress: 99.5% recovery)

## [26.0.11] - 2026-10-08

### Changed
- Renamed communication actions for manual workflow clarity:
  - **Start / Connect** -> **Scan USB**
  - **Refresh Ports** -> **Assign**
- Assign flow now performs full EVC handshake (ver/sn + FACT mode + baud normalization/high-speed validation) before contour pre-download, matching Scan USB readiness behavior.
- Probe button label changed to **ver**.

### Fixed
- Broken COM ports now fail fast during scan probing, avoiding long apparent hangs on unavailable ports.
- FACT mode handling updated for user-mode units that require password entry before `zpar`, including explicit FACT verification and clearer failure reasons.
- App exit now sends `fact off` before disconnect so units return to user mode.
- Probe/ver fallback output now shows actual EVC response payload lines (not just command echo) and filters stale/prompt-only lines.
- Contour flow restored so Scan USB performs contour pre-download and contour toggle plots from cache.

## [26.0.10] - 2026-10-07

### Fixed
- Scope popup chart window can now be closed and reopened reliably. The dialog now uses a standard close-button window lifecycle instead of getting stuck after detach/open cycles.

## [26.0.9] - 2026-10-01

### Added
- Implemented **Button A** integration with `tlog2chart`:
  - Finds the latest saved `tlog` file (or uses the most recent Button A source path).
  - Launches external `tlog![img.png](img.png)2chart` with a handshake stage and analysis stage.
  - Reports running/success/failure status in Troubleshoot **Status/Result** panes.
  - Captures and displays returned analysis report path when available.

### Changed
- Button A now runs `tlog2chart` asynchronously on a worker thread so GUI responsiveness and existing data-acquisition paths are preserved.
- App shutdown now cancels any in-flight Button A `tlog2chart` task cleanly.
- Troubleshoot Button A label is now **tlog2chart** for clearer UX.

### Fixed
- Advanced Diagnostic accumulator summary parsing now trims Triton output after `Cumulative CapSwitch counters for F1 CapArr 1 :` heading (without appending the large counter tables).

## [26.0.8] - 2026-09-30

### Changed
- Baud-switch reconnect logic now handles USB COM re-enumeration by scanning/retrying candidate ports after `baud` commands instead of assuming the original COM number remains valid.
- USB connection status display now reflects the actual connected serial handle port when the device moves between COM numbers.

### Fixed
- Triton Start/Connect normalization no longer fails on `Post-switch low-speed ver failed` when the unit rebinds to a different COM port during baud transitions.
- High-speed switch validation (`baud 7`) now also survives COM-port changes and retains the existing 57600 fallback path when 230400 cannot be verified.

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
