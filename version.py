"""Single source of truth for EVC GUI version information."""
APP_NAME = "EVC GUI"
__version__ = "1.0.4"
VERSION = tuple(int(part) for part in __version__.split("."))
COMPANY = "ASM"
DEPARTMENT = "PEALD RF Engineering"
AUTHOR = "Victor Huang"
CONTACT = "victor.huang@asm.com"

VERSION_HISTORY = [
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
