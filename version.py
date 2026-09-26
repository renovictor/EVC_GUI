"""Single source of truth for EVC GUI version information."""
APP_NAME = "EVC GUI"
__version__ = "1.0.1"
VERSION = tuple(int(part) for part in __version__.split("."))
COMPANY = "ASM"
DEPARTMENT = "PEALD RF Engineering"
AUTHOR = "Victor Huang"
CONTACT = "victor.huang@asm.com"

VERSION_HISTORY = [
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
