import logging
from pathlib import Path
import re
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QGroupBox, QPlainTextEdit, QProgressBar, QTabWidget,
    QMessageBox)
from version import APP_NAME, COMPANY, __version__
from evc_gui.state_machine import EvcStateMachine, AppState
from evc_gui.services.serial_service import SerialService
from evc_gui.logging_config import configure_logging

log = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, asset_dir: Path, log_file: Path):
        super().__init__()
        self.log_file = log_file
        self.serial = SerialService()
        self.machine = EvcStateMachine()
        self.machine.state_changed.connect(self.on_state_changed)
        self.detected_product = "Unknown"
        self.detected_serial_number = ""
        self._device_log_ready = False
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        icon = asset_dir.parent / "smithchart.ico"
        if not icon.exists():
            icon = asset_dir / "smithchart.ico"
        if not icon.exists():
            icon = asset_dir / "evc_gui.ico"
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
        self.resize(1200, 760)
        self._build_ui()
        self.refresh_ports()
        QTimer.singleShot(0, lambda: self.machine.transition(AppState.IDLE, "Initialization complete"))

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        header = QLabel(f"{COMPANY}  |  {APP_NAME}  |  v{__version__}")
        header.setObjectName("header"); header.setAlignment(Qt.AlignCenter); outer.addWidget(header)
        body = QHBoxLayout(); outer.addLayout(body, 1)
        control = QGroupBox("Phase 1: Communication Validation"); form = QGridLayout(control)
        self.product_value = QLabel(self.detected_product)
        self.port = QComboBox(); self.baud = QComboBox(); self.baud.addItems(["9600", "19200", "38400", "57600", "115200"]); self.baud.setCurrentText("57600")
        self.serial_number_value = QLabel("-")
        self.refresh_btn = QPushButton("Refresh Ports"); self.start_btn = QPushButton("Start / Connect"); self.probe_btn = QPushButton("Probe"); self.run_btn = QPushButton("Run"); self.abort_btn = QPushButton("Abort"); self.exit_btn = QPushButton("Exit")
        self.probe_btn.setEnabled(False); self.run_btn.setEnabled(False); self.abort_btn.setEnabled(False)
        widgets = [("Detected Product",self.product_value),("Detected Unit S/N",self.serial_number_value),("COM Port",self.port),("Baud",self.baud)]
        for row,(text,w) in enumerate(widgets): form.addWidget(QLabel(text),row,0); form.addWidget(w,row,1)
        form.addWidget(self.refresh_btn,4,0,1,2); form.addWidget(self.start_btn,5,0,1,2); form.addWidget(self.probe_btn,6,0,1,2); form.addWidget(self.run_btn,7,0,1,2); form.addWidget(self.abort_btn,8,0,1,2); form.addWidget(self.exit_btn,9,0,1,2)
        self.state_label = QLabel("INITIALIZATION"); self.state_label.setObjectName("state"); form.addWidget(QLabel("State"),10,0); form.addWidget(self.state_label,10,1)
        self.progress = QProgressBar(); form.addWidget(self.progress,11,0,1,2)
        form.setRowStretch(12,1); body.addWidget(control,0)
        tabs = QTabWidget(); body.addWidget(tabs,1)
        status_page = QWidget(); status_layout = QVBoxLayout(status_page)
        self.status = QLabel("Initializing..."); self.status.setWordWrap(True); status_layout.addWidget(self.status)
        self.activity = QPlainTextEdit(); self.activity.setReadOnly(True); status_layout.addWidget(self.activity,1)
        tabs.addTab(status_page,"Status")
        for name, note in [("Power Scope","Phase 2 placeholder: Pfwd, Pref, C1, C2, Vpp, DC Bias"),("Smith Chart","Phase 3 placeholder"),("Future","Phase 4 extension area")]:
            page=QWidget(); lay=QVBoxLayout(page); label=QLabel(note); label.setAlignment(Qt.AlignCenter); lay.addWidget(label); tabs.addTab(page,name)
        self.refresh_btn.clicked.connect(self.refresh_ports); self.start_btn.clicked.connect(self.start_connection); self.probe_btn.clicked.connect(self.probe); self.run_btn.clicked.connect(self.run_monitoring); self.abort_btn.clicked.connect(self.abort); self.exit_btn.clicked.connect(self.close)
        self.setStyleSheet("""
            QMainWindow { background:#0e1830; } QWidget { color:#eaf1ff; font-size:14px; }
            QLabel#header { background:#5a36a3; color:white; padding:14px; font-size:22px; font-weight:700; }
            QGroupBox { border:1px solid #47648f; border-radius:10px; margin-top:12px; padding:12px; font-weight:700; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; }
            QPushButton { background:#2463a8; border:none; border-radius:6px; padding:9px; }
            QPushButton:hover { background:#347dca; } QPushButton:disabled { background:#354259; color:#8390a8; }
            QComboBox, QPlainTextEdit { background:#172542; border:1px solid #47648f; border-radius:5px; padding:6px; }
            QTabWidget::pane { border:1px solid #47648f; background:#111f39; }
            QTabBar::tab { background:#253858; padding:9px 18px; } QTabBar::tab:selected { background:#7048b8; }
            QLabel#state { color:#74d7ff; font-weight:800; }
        """)

    def append(self, text): self.activity.appendPlainText(text); self.status.setText(text); log.info(text)
    def refresh_ports(self):
        current=self.port.currentText(); self.port.clear(); self.port.addItems(self.serial.ports())
        if current: self.port.setCurrentText(current)
        self.append(f"COM scan complete: {self.port.count()} port(s) found")

    def start_connection(self):
        if not self.port.currentText(): QMessageBox.warning(self,"No COM Port","Select a COM port first."); return
        self.start_btn.setEnabled(False)
        self.machine.transition(AppState.SCAN_EQUIPMENT, "Preparing scan sequence")
        self.machine.transition(AppState.CHECK_CONNECTION, "Opening serial port")
        result=self.serial.connect(self.port.currentText(), int(self.baud.currentText()))
        self.append(result.message)
        if result.ok:
            self.machine.transition(AppState.GETTING_START,"Communication path validated")
            self.machine.transition(AppState.IDLE,"Ready for probe or run")
            self.probe_btn.setEnabled(True); self.run_btn.setEnabled(True); self.port.setEnabled(False); self.baud.setEnabled(False); self.refresh_btn.setEnabled(False)
        else:
            self.machine.transition(AppState.ERROR,result.message)
            self.start_btn.setEnabled(True)

    def probe(self): self.append(self.serial.probe().message)
    def run_monitoring(self):
        if not self.serial.connected:
            QMessageBox.warning(self, "Not Connected", "Connect to a COM port first.")
            return
        if self.machine.transition(AppState.SCAN_EQUIPMENT,"Run requested"):
            ver_result = self.serial.send_command("ver")
            if not ver_result.ok:
                self.machine.transition(AppState.ERROR, ver_result.message)
                self.append(ver_result.message)
                return
            self.append(f"ver response:\n{ver_result.response}")
            product = self._extract_product_type(ver_result.response)
            if product:
                self.detected_product = product
                self.product_value.setText(product)
                self.append(f"Detected product type: {product}")
            sn_result = self.serial.send_command("sn")
            if not sn_result.ok:
                self.machine.transition(AppState.ERROR, sn_result.message)
                self.append(sn_result.message)
                return
            self.append(f"sn response:\n{sn_result.response}")
            serial_number = self._extract_unit_serial(sn_result.response)
            if serial_number:
                self.detected_serial_number = serial_number
                self.serial_number_value.setText(serial_number)
                if not self._device_log_ready:
                    self.log_file = configure_logging(f"evc_gui_{serial_number}")
                    self._device_log_ready = True
                    self.append(f"Logging switched to {self.log_file.name}")
            self.machine.transition(AppState.CHECK_CONNECTION,"Validate existing connection")
            self.machine.transition(AppState.GETTING_START,"Prepare monitoring")
            self.machine.transition(AppState.RUN,"Phase 1 validation run")
            self.progress.setRange(0,0); self.abort_btn.setEnabled(True); self.run_btn.setEnabled(False); self.start_btn.setEnabled(False); self.append("RUN entered. Phase 2 tlog acquisition is intentionally not enabled yet.")
    def abort(self):
        if self.machine.state==AppState.RUN: self.machine.transition(AppState.IDLE,"User abort")
        self.progress.setRange(0,100); self.progress.setValue(0); self.abort_btn.setEnabled(False); self.run_btn.setEnabled(self.serial.connected); self.append("Run aborted safely")

    @Slot(object,object,str)
    def on_state_changed(self, source, target, reason):
        self.state_label.setText(target.name); self.append(f"{source.name} -> {target.name}: {reason}")

    def closeEvent(self,event):
        try:
            if self.machine.state not in (AppState.IDLE,AppState.ERROR,AppState.CLEANUP,AppState.EXIT): self.machine.transition(AppState.IDLE,"Close requested")
            if self.machine.state in (AppState.IDLE,AppState.ERROR): self.machine.transition(AppState.CLEANUP,"Application closing")
            self.serial.disconnect()
            if self.machine.state==AppState.CLEANUP: self.machine.transition(AppState.EXIT,"Cleanup complete")
            event.accept()
        except Exception:
            log.exception("Unhandled error during close"); event.accept()

    @staticmethod
    def _extract_product_type(response: str) -> str:
        for line in response.splitlines():
            match = re.search(r"^EVC\s+([A-Za-z0-9_-]+)\b", line.strip())
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _extract_unit_serial(response: str) -> str:
        for line in response.splitlines():
            match = re.search(r"Unit\s+S/N:\s*(\S+)", line.strip())
            if match:
                return match.group(1)
        return ""
