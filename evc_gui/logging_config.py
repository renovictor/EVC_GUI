import faulthandler
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def configure_logging() -> Path:
    log_dir = runtime_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "evc_gui.log"
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    console = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    console.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler, console], force=True)
    try:
        fault_file = open(log_dir / "python_fault.log", "a", buffering=1, encoding="utf-8")
        faulthandler.enable(fault_file)
    except OSError:
        logging.getLogger(__name__).exception("Unable to enable faulthandler")
    return log_file
