import logging
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from version import APP_NAME, __version__
from evc_gui.logging_config import configure_logging, runtime_dir
from evc_gui.ui.splash import SplashScreen
from evc_gui.ui.main_window import MainWindow

log = logging.getLogger(__name__)

def exception_hook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback); return
    logging.getLogger("crash").critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    QMessageBox.critical(None,"Unexpected Error",f"{exc_value}\n\nDetails were written to the logs folder.")

def main() -> int:
    log_file = configure_logging(); sys.excepthook = exception_hook
    log.info("Starting %s v%s",APP_NAME,__version__)
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setApplicationVersion(__version__)
    base=runtime_dir(); asset_dir=base/"assets"
    window=MainWindow(asset_dir,log_file)
    splash=SplashScreen(asset_dir,minimum_ms=5000)
    splash.ready.connect(window.show)
    splash.show()
    return app.exec()
