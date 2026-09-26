import faulthandler
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _sanitize_log_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned or "evc_gui"


def configure_logging(log_name: str = "evc_gui") -> Path:
    log_dir = runtime_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{_sanitize_log_name(log_name)}.log"
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    console = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    console.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler, console], force=True)
    try:
        if not faulthandler.is_enabled():
            fault_file = open(log_dir / "python_fault.log", "a", buffering=1, encoding="utf-8")
            faulthandler.enable(fault_file)
    except OSError:
        logging.getLogger(__name__).exception("Unable to enable faulthandler")
    return log_file
