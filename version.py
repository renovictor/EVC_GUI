"""Single source of truth for EVC GUI version information."""
APP_NAME = "EVC GUI"
__version__ = "26.0.14"
VERSION = tuple(int(part) for part in __version__.split("."))
COMPANY = "ASM"
DEPARTMENT = "PEALD RF Engineering"
AUTHOR = "Victor Huang"
CONTACT = "victor.huang@asm.com"

VERSION_HISTORY = [
    {
        "version": "26.0.14",
        "date": "2026-10-10",
        "summary": "Developer scan matrix release: renames contour actions to Single Download Contour and 8 Delay Scan Test, adds timing profile selector support for fixed-profile testing, and introduces 40 Scan Test to run all 40 combinations (5 timing profiles x 8 delay steps) with per-run timing/quality/point summary output.",
    },
    {
        "version": "26.0.13",
        "date": "2026-10-10",
        "summary": "Developer contour tooling release: adds a new Developer tab with manual Download Contour control, configurable inter-command zpar delay (0-200 ms), per-download elapsed-time capture, quality display, and run history to compare link behavior across laptops and environments.",
    },
    {
        "version": "26.0.12",
        "date": "2026-10-09",
        "summary": "ZPAR reliability improvements: eliminates silent data loss by validating response identity (position/band matching), implements automatic retry with clean recovery (3 attempts, exponential backoff), adds adaptive communication quality monitoring (PROBING/GOOD/DEGRADED/POOR/FAILED), provides full diagnostics in CSV (status, attempts, elapsed_ms, recovered_by_retry, error_category, quality_level), ensures transaction safety with thread locks, and includes development-only deterministic fault injection (disabled by default).",
    },
    {
        "version": "26.0.11",
        "date": "2026-10-08",
        "summary": "Serial workflow hardening: Assign/Scan USB flow now supports FACT mode login requirements for zpar on user-mode units, adds FACT-off on exit, improves ver/probe response reporting, and stabilizes contour pre-download/plot behavior.",
    },
    {
        "version": "26.0.10",
        "date": "2026-10-07",
        "summary": "Scope popup close behavior fix: the detached chart window now has a normal close button lifecycle and can be closed/reopened reliably without locking.",
    },
    {
        "version": "26.0.9",
        "date": "2026-10-06",
        "summary": "Advanced diagnostic and device scan refinement: Adv. Diag. now keeps the backup step even when the stat command fails, strips the noisy CapSwitch table from the accumulated summary, adds a cached in-memory backup fast path, and keeps the EVC selection dialog background green while deduplicating scan results by COM port.",
    },
    {
        "version": "26.0.8",
        "date": "2026-09-30",
        "summary": "Triton release hardening: baud-switch recovery now handles COM port re-enumeration after baud changes, retries reconnect/verification across candidate ports, keeps USB state synced with the active port, and preserves low-speed fallback when high-speed validation is unavailable.",
    },
    {
        "version": "26.0.7",
        "date": "2026-09-30",
        "summary": "Acquisition-mode expansion release: Log1/Log2/Log3 workflows with sample-rate benchmarking, tlog rt high-speed streaming support, cross-device tlog parser hardening (Quantum/Triton/Chronos variants), Chronos Log3 fallback to Log2, run-mode tooltips, and product-aware raw filename restoration.",
    },
    {
        "version": "26.0.6",
        "date": "2026-09-30",
        "summary": "Baud-control reliability update: enforced 57600 identity query then 230400 boost, explicit high-speed verification before contour/zpar download, and robust 57600 restore-on-exit with low-speed command fallback and real ver-based confirmation.",
    },
    {
        "version": "26.0.5",
        "date": "2026-09-30",
        "summary": "Performance and diagnostics update: accelerated contour zpar download, robust backup/tlog completion and unsupported-command handling, USB connection-state display, result export on app exit, and improved non-zero demo logging for raw CSV validation.",
    },
    {
        "version": "26.0.4",
        "date": "2026-09-29",
        "summary": "Diagnostic streaming fix: background tlog download with line-by-line status updates, end-marker detection on 'Printed from : EVC', and responsive UI behavior during long serial reads.",
    },
    {
        "version": "26.0.3",
        "date": "2026-09-28",
        "summary": "Diagnostic UI enhancement: 6-button system (Diagnostic, Backup, tlog, Adv. Diag., A, B) with split Status/Result textboxes, real-time streaming layout, device-specific timeouts (5m Chronos 1, 40m Tykon), accumulator info extraction, and timestamped result history.",
    },
    {
        "version": "26.0.2",
        "date": "2026-09-28",
        "summary": "Troubleshooting release: renamed Future tab to Troubleshoot, added Diagnostic button, and implemented stat active-fault parsing with fault-code display (including Tykon 25/43 mapping).",
    },
    {
        "version": "26.0.1",
        "date": "2026-09-28",
        "summary": "UI polish and progress visibility: bright red 40px progress bar with thick styling, visible during contour download, progress updates every 10 queries to avoid serial blocking, larger progress indicator symbol.",
    },
    {
        "version": "26.0.0",
        "date": "2026-09-28",
        "summary": "Quantum release: dual HF/LF parsing, Power Scope HF/LF toggle, dual-band (hf/lf) zpar contour download with shared Smith Chart plotting (HF red, LF blue), plus Chronos generation mapping, robust baud auto-scan/validation, contour automation, and usability improvements.",
    },
    {
        "version": "1.0.5",
        "date": "2026-09-28",
        "summary": "Chronos-focused release: robust baud mismatch recovery with stricter ver handshake, Chronos 1/2.0 SN-based product detection and contour cap-range mapping, contour auto-download after scan, raw-only CSV logging, and Power Scope click-to-edit Y-axis scaling dialog.",
    },
    {
        "version": "1.0.4",
        "date": "2026-09-27",
        "summary": "High-speed serial workflow update: 57600/230400 auto-detection with response-content validation, baud 7 switch-and-verify flow, 75 ms run command timing, 3-hour CSV rotation, expanded raw columns, and Excel-friendly millisecond timestamps.",
    },
    {
        "version": "1.0.3",
        "date": "2026-09-27",
        "summary": "Contour caching and Smith Chart fixes: persistent cached Z-parameter contour, busy download state, one-time contour download, and correct per-line plotting order.",
    },
    {
        "version": "1.0.2",
        "date": "2026-09-27",
        "summary": "Phase 2 completed: pdat1/psum1 acquisition, Power Scope plotting, demo mode, CSV logging, and chart rendering fix.",
    },
    {
        "version": "1.0.1",
        "date": "2026-09-26",
        "summary": "Phase 1 finalized: splash logo, smithchart icon, 57600 default baud, Start/Run guardrails, ver/sn scan parsing, and SN-based logging.",
    },
    {
        "version": "1.0.0",
        "date": "2026-09-26",
        "summary": "Phase 1 foundation: PySide6 GUI, state machine, serial validation, splash screen, logging, and release assets.",
    }
]

def display_version() -> str:
    return f"v{__version__}"
