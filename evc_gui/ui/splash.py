import importlib
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Qt, Signal, QTimer
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QWidget, QLabel, QProgressBar, QVBoxLayout, QHBoxLayout
from version import APP_NAME, COMPANY, DEPARTMENT, AUTHOR, CONTACT, display_version

MODULES = [
    ("PySerial", "serial", False),
    ("Pandas", "pandas", False),
    ("OpenPyXL", "openpyxl", False),
    ("NumPy", "numpy", True),
    ("Matplotlib", "matplotlib", True),
    ("Pillow/PIL", "PIL", True),
    ("python-docx", "docx", True),
    ("guardian_tlog", "guardian_tlog", True),
    ("jsonl_to_excel", "jsonl_to_excel", True),
]

class ModuleLoader(QObject):
    progress = Signal(int, str)
    complete = Signal()

    def run(self):
        total = len(MODULES)
        for i, (label, module_name, optional) in enumerate(MODULES, start=1):
            self.progress.emit(int((i - 1) / total * 100), f"Loading {label}...")
            try:
                importlib.import_module(module_name)
            except ImportError:
                if not optional:
                    self.progress.emit(int(i / total * 100), f"Required module unavailable: {label}")
            self.progress.emit(int(i / total * 100), f"Loaded {label}" if not optional else f"Checked {label}")
        self.complete.emit()

class SplashScreen(QWidget):
    ready = Signal()

    def __init__(self, asset_dir: Path, minimum_ms: int = 5000):
        super().__init__()
        self.minimum_done = False
        self.loading_done = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(700, 400)
        self.setStyleSheet("""
            QWidget { color: white; background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #06162f,stop:.48 #263e78,stop:1 #c4a7e7); }
            QLabel#title { font-size: 30px; font-weight: 700; }
            QLabel#meta { font-size: 14px; color: #f1edff; }
            QProgressBar { border: 1px solid #ddd; border-radius: 8px; background: rgba(255,255,255,40); height: 16px; text-align: center; }
            QProgressBar::chunk { border-radius: 7px; background: #67d4ff; }
            QLabel#footer { background: rgba(4,12,34,150); padding: 10px; color: #dce8ff; }
        """)
        layout = QVBoxLayout(self); layout.setContentsMargins(32, 28, 32, 0); layout.setSpacing(12)
        logo = QLabel(); logo.setAlignment(Qt.AlignCenter)
        gif_path = asset_dir / "ASM-logo-small.gif"
        if gif_path.exists():
            movie = QMovie(str(gif_path)); logo.setMovie(movie); movie.start(); self._movie = movie
        else:
            logo.setText("ASM"); logo.setStyleSheet("font-size: 34px; font-weight: 800;")
        title = QLabel(f"{APP_NAME}  {display_version()}"); title.setObjectName("title"); title.setAlignment(Qt.AlignCenter)
        meta = QLabel(f"{DEPARTMENT}\n{COMPANY}"); meta.setObjectName("meta"); meta.setAlignment(Qt.AlignCenter)
        self.status = QLabel("Starting..."); self.status.setAlignment(Qt.AlignCenter)
        self.bar = QProgressBar(); self.bar.setRange(0, 100)
        footer = QLabel(f"Author: {AUTHOR}  |  Contact: {CONTACT}"); footer.setObjectName("footer"); footer.setAlignment(Qt.AlignCenter)
        for w in (logo, title, meta, self.status, self.bar): layout.addWidget(w)
        layout.addStretch(); layout.addWidget(footer)
        QTimer.singleShot(minimum_ms, self._minimum_elapsed)
        self._thread = QThread(self)
        self._loader = ModuleLoader(); self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.progress.connect(self._on_progress)
        self._loader.complete.connect(self._on_loading_complete)
        self._loader.complete.connect(self._thread.quit)

    def showEvent(self, event):
        super().showEvent(event)
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        if not self._thread.isRunning(): self._thread.start()

    def _on_progress(self, value, text): self.bar.setValue(value); self.status.setText(text)
    def _minimum_elapsed(self): self.minimum_done = True; self._finish_if_ready()
    def _on_loading_complete(self): self.loading_done = True; self.bar.setValue(100); self.status.setText("Ready"); self._finish_if_ready()
    def _finish_if_ready(self):
        if self.minimum_done and self.loading_done:
            self.ready.emit(); self.close()
