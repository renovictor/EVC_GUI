"""Single source of truth for EVC GUI version information."""
APP_NAME = "EVC GUI"
__version__ = "26.0.7"
VERSION = tuple(int(part) for part in __version__.split("."))
COMPANY = "ASM"
DEPARTMENT = "PEALD RF Engineering"
AUTHOR = "Victor Huang"
CONTACT = "victor.huang@asm.com"

VERSION_HISTORY = [
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
