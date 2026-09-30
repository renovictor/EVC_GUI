import csv
import cmath
import logging
import math
import threading
import time
from pathlib import Path
from datetime import datetime
import re
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, Slot, Signal, QObject, QThread
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from evc_gui.logging_config import configure_logging
from evc_gui.services.phase2 import DataController, SerialWorker
from evc_gui.services.serial_service import SerialService
from evc_gui.services.port_scanner import PortScanner
from evc_gui.state_machine import AppState, EvcStateMachine
from evc_gui.ui.power_scope import PowerScopeWidget
from evc_gui.ui.smith_chart import (
    SmithChartWidget,
    ZParameters,
    calculate_load_impedance_from_z_params,
    impedance_to_gamma,
)
from evc_gui.ui.device_selection_dialog import DeviceSelectionDialog
from version import APP_NAME, COMPANY, __version__

log = logging.getLogger(__name__)
LOW_SPEED_BAUD = 57600
HIGH_SPEED_BAUD = 230400
LOW_SPEED_BAUD_COMMAND = "baud 5"
LOW_SPEED_BAUD_COMMAND_FALLBACK = "baud 6"
HIGH_SPEED_BAUD_COMMAND = "baud 7"
START_BAUD_CANDIDATES = (LOW_SPEED_BAUD, HIGH_SPEED_BAUD)
RUN_COMMAND_TIMEOUT_S = 0.075
HANDSHAKE_TIMEOUT_S = 1.0
SCAN_COMMAND_TIMEOUT_S = 0.5
POST_SWITCH_SETTLE_S = 0.35
SAMPLE_RATE_WINDOW_LOOPS = 10
SAMPLE_RATE_REPORT_INTERVAL_S = 5.0
RUN_PROFILE_CONFIGS: dict[str, dict[str, float | int]] = {
    "Baseline": {
        "poll_interval_ms": 120,
        "command_timeout_s": RUN_COMMAND_TIMEOUT_S,
        "ui_update_stride": 1,
        "raw_flush_every_rows": 1,
        "raw_flush_interval_s": 0.2,
    },
    "Aggressive": {
        "poll_interval_ms": 60,
        "command_timeout_s": 0.06,
        "ui_update_stride": 2,
        "raw_flush_every_rows": 10,
        "raw_flush_interval_s": 0.4,
    },
    "Max Throughput": {
        "poll_interval_ms": 30,
        "command_timeout_s": 0.05,
        "ui_update_stride": 3,
        "raw_flush_every_rows": 25,
        "raw_flush_interval_s": 0.6,
    },
}
VER_RETRY_COUNT = 3
SCAN_VER_RETRY_COUNT = 3
ZPAR_COMMAND_TIMEOUT_S = 0.5
ZPAR_READ_TIMEOUT_S = 0.01
ZPAR_PAYLOAD_QUIET_S = 0.03
TLOG_TIMEOUT_S = 300.0
TLOG_MAX_PARTS = 6
TYKON_FAULT_EXPLANATIONS = {
    "25": "Power Supplies Not On",
    "43": "DC Fault (DC PS Setup/Comm)",
}
BACKUP_END_MARKERS = ("Printed from : EVC", "Printed from: EVC")


# Signal emitter for thread-safe scanning completion
class ScanCompleteSignals(QObject):
    scan_complete = Signal(list)  # Emits list of DetectedDevice


@dataclass(frozen=True)
class DiagnosticCommand:
    key: str
    command: str
    timeout: float
    end_markers: tuple[str, ...] = ()
    line_ending: str = "\r\n"
    continue_on_incomplete: bool = False
    max_parts: int = 1


@dataclass(frozen=True)
class DiagnosticCommandResult:
    key: str
    command: str
    ok: bool
    message: str
    response: str


@dataclass(frozen=True)
class DiagnosticJobResult:
    ok: bool
    message: str
    results: dict[str, DiagnosticCommandResult]


class DiagnosticJobWorker(QThread):
    progress = Signal(str)
    line_received = Signal(str)
    job_finished = Signal(object)

    def __init__(self, serial: SerialService, steps: list[DiagnosticCommand]):
        super().__init__()
        self._serial = serial
        self._steps = steps
        self._cancelled = threading.Event()

    def request_cancel(self):
        self._cancelled.set()

    def run(self):
        results: dict[str, DiagnosticCommandResult] = {}
        try:
            for step in self._steps:
                if self._cancelled.is_set():
                    self.job_finished.emit(DiagnosticJobResult(False, "Diagnostic download cancelled", results))
                    return
                max_parts = max(1, step.max_parts)
                part_index = 1
                combined_chunks: list[str] = []
                result = None
                while True:
                    part_label = f" (part {part_index}/{max_parts})" if max_parts > 1 else ""
                    self.progress.emit(f"Sending {step.command}{part_label}...")
                    result = self._serial.send_command(
                        step.command,
                        timeout=step.timeout,
                        cancel_event=self._cancelled,
                        end_markers=step.end_markers,
                        line_callback=self.line_received.emit,
                        line_ending=step.line_ending,
                    )
                    if result.response:
                        combined_chunks.append(result.response)
                    if self._cancelled.is_set():
                        self.job_finished.emit(DiagnosticJobResult(False, "Diagnostic download cancelled", results))
                        return
                    incomplete = (
                        (not result.ok)
                        and ("ended before end marker" in result.message.lower())
                        and bool(result.response.strip())
                    )
                    if step.continue_on_incomplete and incomplete and part_index < max_parts:
                        self.progress.emit(
                            f"{step.command} part {part_index} incomplete; collecting next part..."
                        )
                        part_index += 1
                        continue
                    break
                assert result is not None
                combined_response = "\n".join(chunk for chunk in combined_chunks if chunk).strip()
                result_message = result.message
                if part_index > 1:
                    result_message = f"{result.message} after {part_index} part(s)"
                step_result = DiagnosticCommandResult(
                    key=step.key,
                    command=step.command,
                    ok=result.ok,
                    message=result_message,
                    response=combined_response,
                )
                results[step.key] = step_result
                if not result.ok:
                    message = "Diagnostic download cancelled" if self._cancelled.is_set() else result_message
                    self.job_finished.emit(DiagnosticJobResult(False, message, results))
                    return
            self.job_finished.emit(DiagnosticJobResult(True, "Diagnostic download complete", results))
        except Exception as exc:
            log.exception("Diagnostic worker failed")
            self.job_finished.emit(DiagnosticJobResult(False, f"Diagnostic download failed: {exc}", results))


class MainWindow(QMainWindow):
    def __init__(self, asset_dir: Path, log_file: Path):
        super().__init__()
        self.log_file = log_file
        self.serial = SerialService()
        self.port_scanner = PortScanner()
        self.machine = EvcStateMachine()
        self.machine.state_changed.connect(self.on_state_changed)
        self.detected_product = "Unknown"
        self.detected_serial_number = ""
        self.detected_firmware = ""
        self._active_baud = LOW_SPEED_BAUD
        self._device_log_ready = False
        self._worker: SerialWorker | None = None
        self._diagnostic_worker: DiagnosticJobWorker | None = None
        self._diagnostic_job_kind: str | None = None
        self._diagnostic_timestamp = ""
        self._controller: DataController | None = None
        self._sample_rate_window_timestamps: list[float] = []
        self._sample_rate_hz_windows: list[float] = []
        self._sample_rate_total_samples = 0
        self._sample_rate_last_report_at = 0.0
        self._run_profile_name = "Baseline"
        self._run_ui_update_stride = 1
        self._run_ui_sample_counter = 0
        self._run_mode = "log1"
        self._chart_timer = QTimer(self)
        self._chart_timer.setInterval(250)
        self._chart_timer.timeout.connect(self._refresh_scope)
        # Signal-based scanning (thread-safe)
        self._scan_signals = ScanCompleteSignals()
        self._scan_signals.scan_complete.connect(self._on_auto_scan_complete)
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        icon = asset_dir.parent / "smithchart.ico"
        if not icon.exists():
            icon = asset_dir / "smithchart.ico"
        if not icon.exists():
            icon = asset_dir / "evc_gui.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1280, 800)
        self._build_ui()
        self.refresh_ports()
        QTimer.singleShot(0, lambda: self.machine.transition(AppState.IDLE, "Initialization complete"))

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        header = QLabel(f"{COMPANY}  |  {APP_NAME}  |  v{__version__}")
        header.setObjectName("header")
        header.setAlignment(Qt.AlignCenter)
        outer.addWidget(header)
        body = QHBoxLayout()
        outer.addLayout(body, 1)

        control = QGroupBox("Communication / Run Control")
        form = QGridLayout(control)
        self.product_value = QLabel(self.detected_product)
        self.port = QComboBox()
        self.baud = QComboBox()
        self.baud.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud.setCurrentText(str(LOW_SPEED_BAUD))
        self.run_profile = QComboBox()
        self.run_profile.addItems(list(RUN_PROFILE_CONFIGS.keys()))
        self.run_profile.setCurrentText("Baseline")
        self.serial_number_value = QLabel("-")
        self.refresh_btn = QPushButton("Refresh Ports")
        self.start_btn = QPushButton("Start / Connect")
        self.demo_mode_check = QCheckBox("Demo Mode (Phase 2/3)")
        self.probe_btn = QPushButton("Probe")
        self.log1_btn = QPushButton("Log1")
        self.log2_btn = QPushButton("Log2")
        self.log3_btn = QPushButton("Log3")
        self.log1_btn.setToolTip("Log1: Legacy polling mode using pdat1 + psum1 (2 commands per loop).")
        self.log2_btn.setToolTip("Log2: Single-command mode using tlog 1 (1 command per loop).")
        self.log3_btn.setToolTip("Log3: Streaming mode using tlog rt for highest sample-rate throughput (Chronos falls back to Log2).")
        self.abort_btn = QPushButton("Abort")
        self.exit_btn = QPushButton("Exit")
        self.probe_btn.setEnabled(False)
        self.log1_btn.setEnabled(False)
        self.log2_btn.setEnabled(False)
        self.log3_btn.setEnabled(False)
        self.abort_btn.setEnabled(False)
        widgets = [
            ("Detected Product", self.product_value),
            ("Detected Unit S/N", self.serial_number_value),
            ("COM Port", self.port),
            ("Baud", self.baud),
            ("RUN Profile", self.run_profile),
        ]
        for row, (text, widget) in enumerate(widgets):
            form.addWidget(QLabel(text), row, 0)
            form.addWidget(widget, row, 1)
        control_row = len(widgets)
        form.addWidget(self.refresh_btn, control_row, 0, 1, 2)
        form.addWidget(self.start_btn, control_row + 1, 0, 1, 2)
        form.addWidget(self.demo_mode_check, control_row + 2, 0, 1, 2)
        form.addWidget(self.probe_btn, control_row + 3, 0, 1, 2)
        form.addWidget(self.log1_btn, control_row + 4, 0, 1, 2)
        form.addWidget(self.log2_btn, control_row + 5, 0, 1, 2)
        form.addWidget(self.log3_btn, control_row + 6, 0, 1, 2)
        form.addWidget(self.abort_btn, control_row + 7, 0, 1, 2)
        form.addWidget(self.exit_btn, control_row + 8, 0, 1, 2)
        self.state_label = QLabel("INITIALIZATION")
        self.state_label.setObjectName("state")
        form.addWidget(QLabel("State"), control_row + 9, 0)
        form.addWidget(self.state_label, control_row + 9, 1)
        self.usb_state_label = QLabel("Disconnected")
        self.usb_state_label.setObjectName("state")
        form.addWidget(QLabel("USB State"), control_row + 10, 0)
        form.addWidget(self.usb_state_label, control_row + 10, 1)
        self.progress = QProgressBar()
        self.progress.setMinimumHeight(40)  # Make progress indicator noticeably larger
        # Style progress bar: red chunk and thicker appearance
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #333;
                border-radius: 5px;
                background-color: #222;
                height: 35px;
            }
            QProgressBar::chunk {
                background-color: #FF0000;
                border-radius: 3px;
            }
        """)
        form.addWidget(self.progress, control_row + 11, 0, 1, 2)
        form.setRowStretch(control_row + 12, 1)
        body.addWidget(control, 0)

        tabs = QTabWidget()
        body.addWidget(tabs, 1)
        status_page = QWidget()
        status_layout = QVBoxLayout(status_page)
        self.status = QLabel("Initializing...")
        self.status.setWordWrap(True)
        status_layout.addWidget(self.status)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        status_layout.addWidget(self.activity, 1)
        tabs.addTab(status_page, "Status")

        self.power_scope = PowerScopeWidget()
        tabs.addTab(self.power_scope, "Power Scope")
        self.smith_chart = SmithChartWidget()
        tabs.addTab(self.smith_chart, "Smith Chart")
        troubleshoot_page = QWidget()
        troubleshoot_layout = QVBoxLayout(troubleshoot_page)
        
        # Create diagnostic buttons in a grid layout
        diag_buttons_layout = QGridLayout()
        self.diagnostic_btn = QPushButton("Diagnostic")
        self.backup_btn = QPushButton("Backup")
        self.tlog_btn = QPushButton("tlog")
        self.adv_diag_btn = QPushButton("Adv. Diag.")
        self.button_a = QPushButton("A")
        self.button_b = QPushButton("B")
        
        diag_buttons_layout.addWidget(self.diagnostic_btn, 0, 0)
        diag_buttons_layout.addWidget(self.backup_btn, 0, 1)
        diag_buttons_layout.addWidget(self.tlog_btn, 0, 2)
        diag_buttons_layout.addWidget(self.adv_diag_btn, 1, 0)
        diag_buttons_layout.addWidget(self.button_a, 1, 1)
        diag_buttons_layout.addWidget(self.button_b, 1, 2)
        
        troubleshoot_layout.addLayout(diag_buttons_layout)
        
        # Split into Status (left) and Result (right)
        content_layout = QHBoxLayout()
        
        # Status box (real-time messages)
        status_container = QWidget()
        status_layout = QVBoxLayout(status_container)
        status_label = QLabel("Status")
        status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(status_label)
        self.diagnostic_status = QPlainTextEdit()
        self.diagnostic_status.setReadOnly(True)
        self.diagnostic_status.setPlaceholderText("Real-time status messages from EVC will appear here.")
        status_layout.addWidget(self.diagnostic_status, 1)
        
        # Result box (accumulated results with timestamps)
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_label = QLabel("Result")
        result_label.setStyleSheet("font-weight: bold;")
        result_layout.addWidget(result_label)
        self.diagnostic_output = QPlainTextEdit()
        self.diagnostic_output.setReadOnly(True)
        self.diagnostic_output.setPlaceholderText("Diagnostic results with timestamps will accumulate here.")
        result_layout.addWidget(self.diagnostic_output, 1)
        
        content_layout.addWidget(status_container, 1)
        content_layout.addWidget(result_container, 1)
        troubleshoot_layout.addLayout(content_layout, 1)
        tabs.addTab(troubleshoot_page, "Troubleshoot")

        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.start_btn.clicked.connect(self.start_connection)
        self.demo_mode_check.toggled.connect(self._on_demo_mode_toggled)
        self.smith_chart.contour_check.toggled.connect(self._on_contour_toggled)
        self.probe_btn.clicked.connect(self.probe)
        self.diagnostic_btn.clicked.connect(self.run_diagnostic)
        self.backup_btn.clicked.connect(self.run_backup)
        self.tlog_btn.clicked.connect(self.run_tlog)
        self.adv_diag_btn.clicked.connect(self.run_adv_diagnostic)
        self.button_a.clicked.connect(self.run_button_a)
        self.button_b.clicked.connect(self.run_button_b)
        self.log1_btn.clicked.connect(self.run_log1)
        self.log2_btn.clicked.connect(self.run_log2)
        self.log3_btn.clicked.connect(self.run_log3)
        self.abort_btn.clicked.connect(self.abort)
        self.exit_btn.clicked.connect(self.close)
        self.setStyleSheet(
            """
            QMainWindow { background:#0e1830; } QWidget { color:#eaf1ff; font-size:14px; }
            QLabel#header { background:#5a36a3; color:white; padding:14px; font-size:22px; font-weight:700; }
            QGroupBox { border:1px solid #47648f; border-radius:10px; margin-top:12px; padding:12px; font-weight:700; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; }
            QPushButton { background:#2463a8; border:none; border-radius:6px; padding:9px; }
            QPushButton:hover { background:#347dca; } QPushButton:disabled { background:#354259; color:#8390a8; }
            QComboBox, QPlainTextEdit, QLineEdit { background:#172542; border:1px solid #47648f; border-radius:5px; padding:6px; }
            QTabWidget::pane { border:1px solid #47648f; background:#111f39; }
            QTabBar::tab { background:#253858; padding:9px 18px; } QTabBar::tab:selected { background:#7048b8; }
            QLabel#state { color:#74d7ff; font-weight:800; }
        """
        )

    def append(self, text: str):
        self.activity.appendPlainText(text)
        self.status.setText(text)
        log.info(text)

    def _update_usb_state_label(self):
        if self.serial.connected:
            port = self.port.currentText().strip() or "Unknown"
            self.usb_state_label.setText(f"Connected ({port} @ {self._active_baud})")
        else:
            self.usb_state_label.setText("Disconnected")

    def _connected_baudrate(self) -> int | None:
        serial_handle = getattr(self.serial, "_serial", None)
        if not serial_handle:
            return None
        try:
            baud = int(serial_handle.baudrate)
        except (TypeError, ValueError, AttributeError):
            return None
        return baud

    def refresh_ports(self):
        current = self.port.currentText()
        self.port.clear()
        self.port.addItems(self.serial.ports())
        if current:
            self.port.setCurrentText(current)
        self._update_controls_for_idle()
        self.append(f"COM scan complete: {self.port.count()} port(s) found")

    def start_connection(self):
        """Start connection with auto-scan and device selection."""
        self.start_btn.setEnabled(False)
        self.append("Scanning COM ports for EVC devices...")
        self.progress.setRange(0, 0)  # Indeterminate progress
        
        # Start scanning in background
        import threading
        self._scan_thread = threading.Thread(target=self._scan_and_select_device, daemon=True)
        self._scan_thread.start()
    
    def _scan_and_select_device(self):
        """Scan for devices and show selection dialog (runs in background thread)."""
        try:
            devices = self.port_scanner.scan_ports()
            # Emit signal to notify main thread (thread-safe)
            self._scan_signals.scan_complete.emit(devices)
        except Exception as exc:
            log.exception("Error scanning ports")
            # Emit empty list on error
            self._scan_signals.scan_complete.emit([])
    
    @Slot(list)
    def _on_auto_scan_complete(self, devices: list):
        """Handle auto-scan completion (called on main thread)."""
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        
        if not devices:
            QMessageBox.warning(
                self, "No Devices Found",
                "No EVC devices detected on available COM ports.\n\n"
                "Possible issues:\n"
                "• Device not connected\n"
                "• Device is not responding\n"
                "• Wrong baud rate\n\n"
                "Please check your device and try again."
            )
            self.start_btn.setEnabled(True)
            self.append("Device scan failed: no devices detected")
            return
        
        # Show device selection dialog
        dialog = DeviceSelectionDialog(devices, self)
        dialog.setStyleSheet(self.styleSheet())  # Apply app styling
        
        if dialog.exec() == QDialog.Accepted:
            # Check if user selected manual mode
            if getattr(dialog, 'use_manual', False):
                self.start_btn.setEnabled(True)
                self.append("Switched to manual port selection")
                return
            
            selected = dialog.get_selected_device()
            if selected:
                self._connect_to_device(selected)
        else:
            self.start_btn.setEnabled(True)
            self.append("Device selection cancelled")
    
    def _connect_to_device(self, device):
        """Connect to the selected device."""
        self.append(f"Connecting to {device.product} on {device.port} @ {device.baudrate} baud...")
        self.start_btn.setEnabled(False)
        self.machine.transition(AppState.SCAN_EQUIPMENT, "Preparing scan sequence")
        self.machine.transition(AppState.CHECK_CONNECTION, "Opening serial port")
        
        # Connect to the selected port and baud rate
        result = self.serial.connect(device.port, device.baudrate)
        self.append(result.message)
        if result.ok:
            self._active_baud = device.baudrate
        self._update_usb_state_label()
        if not result.ok:
            self.machine.transition(AppState.ERROR, f"Connection failed: {result.message}")
            self.start_btn.setEnabled(True)
            self._update_controls_for_idle()
            return
        
        # Validate identity
        if not self._switch_to_low_speed(fail_on_error=False):
            self.append("Failed to normalize to 57600 baud before identity validation")
            self.serial.disconnect()
            self._update_usb_state_label()
            self.machine.transition(AppState.ERROR, "Failed to switch to 57600 baud")
            self.start_btn.setEnabled(True)
            self._update_controls_for_idle()
            return

        if not self._query_scan_identity(setup_device_log=False, fail_on_error=False):
            self.append("Identity validation failed")
            self.serial.disconnect()
            self._update_usb_state_label()
            self.machine.transition(AppState.ERROR, "Identity validation failed")
            self.start_btn.setEnabled(True)
            self._update_controls_for_idle()
            return

        if not self._switch_to_high_speed():
            self.append("Failed to switch to 230400 baud after identity validation")
            self.serial.disconnect()
            self._update_usb_state_label()
            self.start_btn.setEnabled(True)
            self._update_controls_for_idle()
            return
        
        self.append(f"Handshake OK at {self._active_baud} baud")
        self.port.setCurrentText(device.port)
        self.baud.setCurrentText(str(self._active_baud))
        
        # Update UI
        self.machine.transition(AppState.GETTING_START, "Communication path validated")
        self.machine.transition(AppState.IDLE, "Ready for probe or run")
        self._auto_download_contour_after_scan()
        self.probe_btn.setEnabled(True)
        self.port.setEnabled(False)
        self.baud.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self._update_controls_for_idle()


    def probe(self):
        self.append(self.serial.probe().message)

    def _start_diagnostic_job(self, kind: str, steps: list[DiagnosticCommand], start_message: str) -> bool:
        if self._diagnostic_worker and self._diagnostic_worker.isRunning():
            self.append("A diagnostic download is already running.")
            return False
        if not self.machine.transition(AppState.DOWNLOADING_DIAGNOSTIC, start_message):
            return False
        self._diagnostic_job_kind = kind
        self._diagnostic_timestamp = datetime.now().strftime("%Y/%m/%d %H:%M")
        self.diagnostic_status.setPlainText(start_message)
        self.append(start_message)
        self._update_controls_for_idle()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.abort_btn.setEnabled(True)
        self._diagnostic_worker = DiagnosticJobWorker(self.serial, steps)
        self._diagnostic_worker.progress.connect(self._on_diagnostic_progress)
        self._diagnostic_worker.line_received.connect(self._on_diagnostic_line)
        self._diagnostic_worker.job_finished.connect(self._on_diagnostic_job_finished)
        self._diagnostic_worker.start()
        return True

    def _cancel_diagnostic_job(self):
        worker = self._diagnostic_worker
        if not worker:
            return
        worker.request_cancel()
        worker.wait(3000)
        if worker.isRunning():
            log.warning("Diagnostic worker did not stop within the timeout")
        self._diagnostic_worker = None
        self._diagnostic_job_kind = None
        self._diagnostic_timestamp = ""

    @Slot(str)
    def _on_diagnostic_progress(self, message: str):
        self.append(message)

    @Slot(str)
    def _on_diagnostic_line(self, line: str):
        if line:
            self.diagnostic_status.appendPlainText(line)

    def _result_for_key(self, result: DiagnosticJobResult, key: str) -> DiagnosticCommandResult | None:
        return result.results.get(key)

    @Slot(object)
    def _on_diagnostic_job_finished(self, result):
        worker = self.sender()
        if worker is not self._diagnostic_worker:
            return
        kind = self._diagnostic_job_kind or "diagnostic"
        timestamp = self._diagnostic_timestamp or datetime.now().strftime("%Y/%m/%d %H:%M")
        diagnostic_worker = self._diagnostic_worker
        try:
            if diagnostic_worker:
                diagnostic_worker.line_received.disconnect(self._on_diagnostic_line)
        except (RuntimeError, TypeError, AttributeError):
            pass
        self._diagnostic_worker = None
        self._diagnostic_job_kind = None
        self._diagnostic_timestamp = ""
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        try:
            if kind == "diagnostic":
                self._handle_stat_result(timestamp, result)
            elif kind == "backup":
                self._handle_backup_result(timestamp, result)
            elif kind == "tlog":
                self._handle_tlog_result(timestamp, result)
            elif kind == "adv_diag":
                self._handle_advanced_diagnostic_result(timestamp, result)
            else:
                self.append(f"Unexpected diagnostic job kind: {kind}")
        finally:
            if self.machine.state == AppState.DOWNLOADING_DIAGNOSTIC:
                if result.ok:
                    reason = f"{kind} complete"
                elif result.message == "Diagnostic download cancelled":
                    reason = f"{kind} cancelled"
                else:
                    reason = f"{kind} complete with error"
                self.machine.transition(AppState.IDLE, reason)
            self._update_controls_for_idle()

    def _handle_stat_result(self, timestamp: str, result: DiagnosticJobResult):
        stat_result = self._result_for_key(result, "stat")
        if not stat_result:
            output = self._append_result(f"{timestamp} Diagnostic: No response")
            self.diagnostic_output.setPlainText(output)
            self.append("Diagnostic failed: no response")
            return
        self.diagnostic_status.setPlainText(stat_result.response)
        if not stat_result.ok:
            output = self._append_result(f"{timestamp} Diagnostic: Command failed - {stat_result.message}")
            self.diagnostic_output.setPlainText(output)
            self.append(f"Diagnostic failed: {stat_result.message}")
            return
        faults = self._extract_active_faults(stat_result.response)
        if not faults:
            output = self._append_result(f"{timestamp} Diagnostic: No active faults or alarms detected.")
            self.diagnostic_output.setPlainText(output)
            self.append("Diagnostic complete: no active faults found")
            return
        lines = [f"{timestamp} Diagnostic:"]
        lines.append("Active faults detected:")
        for code, description in faults:
            fault_description = TYKON_FAULT_EXPLANATIONS.get(code, description)
            lines.append(f"  {code} -- {fault_description}")
        output = self._append_result("\n".join(lines))
        self.diagnostic_output.setPlainText(output)
        self.append("Diagnostic complete: active faults detected")

    def _handle_backup_result(self, timestamp: str, result: DiagnosticJobResult):
        backup_result = self._result_for_key(result, "back")
        if not backup_result:
            output = self._append_result(f"{timestamp} Backup: No response")
            self.diagnostic_output.setPlainText(output)
            self.append("Backup failed: no response")
            return
        self.diagnostic_status.setPlainText(backup_result.response)
        if self._is_invalid_command_response(backup_result.response):
            output = self._append_result(f"{timestamp} Backup: Unsupported on this EVC (Invalid Command).")
            self.diagnostic_output.setPlainText(output)
            self.append("Backup unavailable: EVC responded 'Invalid Command'")
            return
        if not backup_result.ok:
            output = self._append_result(f"{timestamp} Backup: Command failed - {backup_result.message}")
            self.diagnostic_output.setPlainText(output)
            self.append(f"Backup failed: {backup_result.message}")
            return
        prefix = self._diagnostic_file_prefix()
        now = datetime.now()
        datecode = now.strftime("%Y%m%d")
        timecode = now.strftime("%H%M")
        filename = f"{prefix}_{datecode}_{timecode}_back.txt"
        log_dir = self.log_file.parent if self.log_file else Path.cwd()
        log_dir.mkdir(parents=True, exist_ok=True)
        backup_path = log_dir / filename
        try:
            backup_path.write_text(backup_result.response, encoding="utf-8")
            output = self._append_result(f"{timestamp} Backup: Downloaded successfully.\nSaved to: {backup_path}")
            self.diagnostic_output.setPlainText(output)
            self.append(f"Backup complete: saved to {backup_path}")
        except Exception as e:
            output = self._append_result(f"{timestamp} Backup: Failed to save - {e}")
            self.diagnostic_output.setPlainText(output)
            self.append(f"Backup save failed: {e}")

    def _handle_tlog_result(self, timestamp: str, result: DiagnosticJobResult):
        tlog_result = self._result_for_key(result, "tlog")
        if not tlog_result:
            output = self._append_result(f"{timestamp} tlog: No response")
            self.diagnostic_output.setPlainText(output)
            self.append("Time log failed: no response")
            return
        response_text = tlog_result.response or ""
        self.diagnostic_status.setPlainText(response_text)
        if "The log is empty" in response_text:
            output = self._append_result(f"{timestamp} tlog: Empty (no data in buffer)")
            self.diagnostic_output.setPlainText(output)
            self.append("Time log download complete: log is empty")
            return
        incomplete_timeout = (
            (not tlog_result.ok)
            and "ended before end marker" in tlog_result.message.lower()
            and bool(response_text.strip())
        )
        if (not tlog_result.ok) and (not incomplete_timeout):
            output = self._append_result(f"{timestamp} tlog: Command failed - {tlog_result.message}")
            self.diagnostic_output.setPlainText(output)
            self.append(f"Time log failed: {tlog_result.message}")
            return
        prefix = self._diagnostic_file_prefix()
        now = datetime.now()
        datecode = now.strftime("%Y%m%d")
        timecode = now.strftime("%H%M")
        filename = (
            f"{prefix}_{datecode}_{timecode}_tlog_partial.txt"
            if incomplete_timeout
            else f"{prefix}_{datecode}_{timecode}_tlog.txt"
        )
        log_dir = self.log_file.parent if self.log_file else Path.cwd()
        log_dir.mkdir(parents=True, exist_ok=True)
        tlog_path = log_dir / filename
        try:
            tlog_path.write_text(response_text, encoding="utf-8")
            if incomplete_timeout:
                output = self._append_result(
                    f"{timestamp} tlog: Timed out before footer; partial log saved.\nSaved to: {tlog_path}"
                )
                self.append(f"Time log partial: saved to {tlog_path}")
            else:
                output = self._append_result(f"{timestamp} tlog: Downloaded successfully.\nSaved to: {tlog_path}")
                self.append(f"Time log complete: saved to {tlog_path}")
            self.diagnostic_output.setPlainText(output)
        except Exception as e:
            output = self._append_result(f"{timestamp} tlog: Failed to save - {e}")
            self.diagnostic_output.setPlainText(output)
            self.append(f"Time log save failed: {e}")

    def _handle_advanced_diagnostic_result(self, timestamp: str, result: DiagnosticJobResult):
        stat_result = self._result_for_key(result, "stat")
        backup_result = self._result_for_key(result, "back")
        diag_output: list[str] = []
        if stat_result and stat_result.ok:
            self.diagnostic_status.setPlainText(stat_result.response)
            faults = self._extract_active_faults(stat_result.response)
            if faults:
                diag_output.append("Active faults detected:")
                for code, description in faults:
                    fault_description = TYKON_FAULT_EXPLANATIONS.get(code, description)
                    diag_output.append(f"  {code} -- {fault_description}")
            else:
                diag_output.append("No active faults or alarms detected.")
        elif stat_result:
            self.diagnostic_status.setPlainText(stat_result.response)
            diag_output.append(f"Diagnostic command failed: {stat_result.message}")
        else:
            diag_output.append("Diagnostic command failed: no response")
        if not backup_result:
            output = self._append_result(f"{timestamp} Adv. Diag.: Failed to download backup - no response")
            self.diagnostic_output.setPlainText(output)
            self.append("Advanced diagnostic: backup download failed")
            return
        self.diagnostic_status.setPlainText(backup_result.response)
        if self._is_invalid_command_response(backup_result.response):
            output = self._append_result(
                f"{timestamp} Adv. Diag.: Backup unsupported on this EVC (Invalid Command)."
            )
            self.diagnostic_output.setPlainText(output)
            self.append("Advanced diagnostic: backup unavailable (Invalid Command)")
            return
        if not backup_result.ok:
            output = self._append_result(f"{timestamp} Adv. Diag.: Failed to download backup - {backup_result.message}")
            self.diagnostic_output.setPlainText(output)
            self.append("Advanced diagnostic: backup download failed")
            return
        accu_info = self._extract_accumulator_info(backup_result.response)
        result_lines = [f"{timestamp} Adv. Diag.:"] + diag_output
        if accu_info:
            result_lines.append("\n=== Accumulated Information ===")
            result_lines.extend(accu_info.split('\n'))
        output = self._append_result("\n".join(result_lines))
        self.diagnostic_output.setPlainText(output)
        self.append("Advanced diagnostic complete")

    def run_diagnostic(self):
        if not self.serial.connected:
            message = "Diagnostic unavailable: connect to an EVC first."
            self.diagnostic_status.setPlainText(message)
            self.append(message)
            return
        self._start_diagnostic_job(
            "diagnostic",
            [DiagnosticCommand("stat", "stat", 2.0)],
            "Downloading diagnostic data...",
        )

    @staticmethod
    def _extract_active_faults(response: str) -> list[tuple[str, str]]:
        faults: list[tuple[str, str]] = []
        in_active_faults = False
        for raw_line in response.splitlines():
            line = raw_line.strip()
            if not in_active_faults:
                if line.lower().startswith("active faults"):
                    in_active_faults = True
                continue
            if not line:
                if faults:
                    break
                continue
            if line.lower() == "none":
                break
            if line.endswith(">") and " " not in line:
                break
            match = re.match(r"^(\d+)\s*--\s*(.+)$", line)
            if match:
                faults.append((match.group(1), match.group(2).strip()))
            elif faults:
                break
        return faults

    @staticmethod
    def _is_invalid_command_response(response: str) -> bool:
        return "invalid command" in response.lower()

    def run_backup(self):
        """Download backup file from EVC"""
        if not self.serial.connected:
            message = "Backup unavailable: connect to an EVC first."
            self.diagnostic_status.setPlainText(message)
            self.append(message)
            return
        self._start_diagnostic_job(
            "backup",
            [DiagnosticCommand("back", "back", 120.0, BACKUP_END_MARKERS, "\r")],
            "Starting backup download (waiting for 'Printed from : EVC')...",
        )

    def run_tlog(self):
        """Download time log from EVC with end marker detection"""
        if not self.serial.connected:
            message = "Time log unavailable: connect to an EVC first."
            self.diagnostic_status.setPlainText(message)
            self.append(message)
            return
        is_chronos1 = self._is_chronos_family() and self._is_chronos_legacy_unit()
        timeout_seconds = TLOG_TIMEOUT_S
        device_note = "Chronos 1" if is_chronos1 else "other devices"
        self._start_diagnostic_job(
            "tlog",
            [
                DiagnosticCommand(
                    "tlog",
                    "tlog",
                    timeout_seconds,
                    ("Printed from : EVC", "Printed from: EVC"),
                    "\r",
                    continue_on_incomplete=True,
                    max_parts=TLOG_MAX_PARTS,
                )
            ],
            f"Starting time log download ({device_note}, waiting for 'Printed from : EVC', auto multi-part up to {TLOG_MAX_PARTS})...",
        )

    def run_adv_diagnostic(self):
        """Advanced diagnostic: read backup file and extract accumulator info"""
        if not self.serial.connected:
            message = "Advanced diagnostic unavailable: connect to an EVC first."
            self.diagnostic_status.setPlainText(message)
            self.append(message)
            return
        self._start_diagnostic_job(
            "adv_diag",
            [
               DiagnosticCommand("stat", "stat", 2.0),
               DiagnosticCommand("back", "back", 120.0, BACKUP_END_MARKERS, "\r"),
            ],
            "Starting advanced diagnostic (downloading backup and extracting accumulator info)...",
        )

    def _append_result(self, new_content: str) -> str:
        """Append new timestamped result to existing results without erasing"""
        current = self.diagnostic_output.toPlainText()
        if current and not current.endswith('\n\n'):
            output = current + "\n\n" + new_content
        else:
            output = current + "\n" + new_content if current else new_content
        return output

    def _save_result_text(self):
        output = self.diagnostic_output.toPlainText().strip()
        if not output:
            return
        prefix = self._diagnostic_file_prefix()
        now = datetime.now()
        datecode = now.strftime("%Y%m%d")
        timecode = now.strftime("%H%M%S")
        filename = f"{prefix}_{datecode}_{timecode}_result.txt"
        log_dir = self.log_file.parent if self.log_file else Path.cwd()
        log_dir.mkdir(parents=True, exist_ok=True)
        result_path = log_dir / filename
        try:
            result_path.write_text(output, encoding="utf-8")
        except Exception as exc:
            log.warning("Failed to save result text file: %s", exc)

    def _diagnostic_file_prefix(self) -> str:
        sn = self.detected_serial_number or "UNKNOWN"
        product = re.sub(r"[^0-9A-Za-z_-]", "", self.detected_product or "") or "Unknown"
        return f"{sn}{product}_GUI"

    @staticmethod
    def _extract_accumulator_info(response: str) -> str:
        """Extract accumulator information from backup response"""
        lines = response.splitlines()
        accu_lines = []
        in_accu_section = False
        
        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            
            # Start collecting when we find "Flash Write count"
            if "Flash Write count" in line:
               in_accu_section = True
               accu_lines.append(line)
               continue
            
            if not in_accu_section:
               continue
            
            # Stop collecting after "DNet Lost Comm"
            if "DNet Lost Comm" in line:
               accu_lines.append(line)
               break
            
            # Add lines within the accumulator section
            if in_accu_section:
               if line and not line.endswith(">"):
                   accu_lines.append(line)
        
        return "\n".join(accu_lines) if accu_lines else ""

    def run_button_a(self):
        """Placeholder for button A - reserved for tlog2chart in future"""
        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M")
        output = self._append_result(f"{timestamp} Button A: Not yet implemented (reserved for tlog2chart)")
        self.diagnostic_output.setPlainText(output)
        self.append("Button A: Not yet implemented")

    def run_button_b(self):
        """Placeholder for button B - reserved for Palantir in future"""
        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M")
        output = self._append_result(f"{timestamp} Button B: Not yet implemented (reserved for Palantir)")
        self.diagnostic_output.setPlainText(output)
        self.append("Button B: Not yet implemented")

    def _reset_sample_rate_benchmark(self):
        self._sample_rate_window_timestamps = []
        self._sample_rate_hz_windows = []
        self._sample_rate_total_samples = 0
        self._sample_rate_last_report_at = 0.0

    def _sample_rate_summary(self) -> str | None:
        if not self._sample_rate_hz_windows:
            return None
        current_hz = self._sample_rate_hz_windows[-1]
        avg_hz = sum(self._sample_rate_hz_windows) / len(self._sample_rate_hz_windows)
        min_hz = min(self._sample_rate_hz_windows)
        max_hz = max(self._sample_rate_hz_windows)
        return (
            f"Sample rate (10-loop): current={current_hz:.2f} Hz, "
            f"avg={avg_hz:.2f} Hz, min={min_hz:.2f} Hz, max={max_hz:.2f} Hz, "
            f"windows={len(self._sample_rate_hz_windows)}"
        )

    def _record_sample_rate_benchmark(self):
        now = time.perf_counter()
        self._sample_rate_total_samples += 1
        self._sample_rate_window_timestamps.append(now)
        window_size = SAMPLE_RATE_WINDOW_LOOPS + 1
        if len(self._sample_rate_window_timestamps) > window_size:
            self._sample_rate_window_timestamps = self._sample_rate_window_timestamps[-window_size:]
        if len(self._sample_rate_window_timestamps) < window_size:
            return
        elapsed = self._sample_rate_window_timestamps[-1] - self._sample_rate_window_timestamps[0]
        if elapsed <= 0:
            return
        rate_hz = SAMPLE_RATE_WINDOW_LOOPS / elapsed
        self._sample_rate_hz_windows.append(rate_hz)
        if (now - self._sample_rate_last_report_at) < SAMPLE_RATE_REPORT_INTERVAL_S:
            return
        self._sample_rate_last_report_at = now
        summary = self._sample_rate_summary()
        if summary:
            self.append(summary)

    def _selected_run_profile(self) -> tuple[str, dict[str, float | int]]:
        profile_name = self.run_profile.currentText().strip() or "Baseline"
        config = RUN_PROFILE_CONFIGS.get(profile_name, RUN_PROFILE_CONFIGS["Baseline"])
        return profile_name, config

    def run_log1(self):
        self.run_monitoring("log1")

    def run_log2(self):
        self.run_monitoring("log2")

    def run_log3(self):
        self.run_monitoring("log3")

    def run_monitoring(self, mode: str = "log1"):
        mode = (mode or "log1").strip().lower()
        if mode not in {"log1", "log2", "log3"}:
            mode = "log1"
        self._run_mode = mode
        demo_mode = self.demo_mode_check.isChecked()
        profile_name, profile_config = self._selected_run_profile()
        self._run_profile_name = profile_name
        self._run_ui_update_stride = max(1, int(profile_config["ui_update_stride"]))
        self._run_ui_sample_counter = 0
        self.smith_chart.reset_points()
        self.smith_chart.set_demo_mode(demo_mode)
        if demo_mode and mode != "log1":
            QMessageBox.warning(self, "Demo Mode", "Log2/Log3 are not supported in Demo Mode. Use Log1.")
            return
        if not demo_mode and not self.serial.connected:
            QMessageBox.warning(self, "Not Connected", "Connect to a COM port first.")
            return
        if not self.machine.transition(AppState.SCAN_EQUIPMENT, "Run requested"):
            return
        if demo_mode:
            self.detected_product = "DEMO"
            self.detected_serial_number = "DEMO"
            self.detected_firmware = "DEMO_MODE"
            self.product_value.setText(self.detected_product)
            self.serial_number_value.setText(self.detected_serial_number)
            if not self._device_log_ready:
                self.log_file = configure_logging("evc_gui_demo")
                self._device_log_ready = True
                self.append(f"Logging switched to {self.log_file.name}")
            self.append("Demo mode enabled: generating synthetic pdat1/psum1 stream.")
        else:
            if not self._switch_to_low_speed(fail_on_error=True):
                return
            if not self._query_scan_identity(setup_device_log=True, fail_on_error=True):
                return
            if mode == "log3" and self._is_chronos_family():
                self.append("LOG3 (tlog rt) is not supported on Chronos. Falling back to LOG2 (tlog 1).")
                mode = "log2"
                self._run_mode = "log2"
            if not self._switch_to_high_speed():
                return

        self.machine.transition(AppState.CHECK_CONNECTION, "Validate existing connection")
        self.machine.transition(AppState.GETTING_START, "Prepare monitoring")
        self.machine.transition(AppState.RUN, f"Phase 2 data acquisition run ({mode.upper()})")
        self.progress.setRange(0, 0)
        self.abort_btn.setEnabled(True)
        self.log1_btn.setEnabled(False)
        self.log2_btn.setEnabled(False)
        self.log3_btn.setEnabled(False)
        self.probe_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.demo_mode_check.setEnabled(False)
        self.run_profile.setEnabled(False)
        # Disable diagnostic buttons during run
        self.diagnostic_btn.setEnabled(False)
        self.backup_btn.setEnabled(False)
        self.tlog_btn.setEnabled(False)
        self.adv_diag_btn.setEnabled(False)
        self.button_a.setEnabled(False)
        self.button_b.setEnabled(False)
        if self.smith_chart.contour_check.isChecked():
            self.smith_chart.show_contour(True)
        self._reset_sample_rate_benchmark()
        self.append(
            f"RUN profile: {self._run_profile_name} "
            f"(poll={int(profile_config['poll_interval_ms'])}ms, "
            f"cmd_timeout={float(profile_config['command_timeout_s']):.3f}s, "
            f"ui_stride={self._run_ui_update_stride}, "
            f"log_flush_rows={int(profile_config['raw_flush_every_rows'])})"
        )
        self._start_phase2_pipeline(demo_mode=demo_mode, mode=mode)
        if demo_mode:
            self.append("LOG1 entered. Feeding demo data into Power Scope.")
        else:
            mode_message = {
                "log1": "LOG1 entered. Querying pdat1 + psum1 and updating Power Scope.",
                "log2": "LOG2 entered. Querying tlog 1 and updating Power Scope.",
                "log3": "LOG3 entered. Streaming tlog rt and updating Power Scope.",
            }
            self.append(mode_message.get(mode, "RUN entered."))

    def abort(self):
        if self._diagnostic_worker and self._diagnostic_worker.isRunning():
            self._cancel_diagnostic_job()
            self.diagnostic_status.setPlainText("Diagnostic download cancelled.")
            self.append("Diagnostic download cancelled")
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.abort_btn.setEnabled(False)
            if self.machine.state == AppState.DOWNLOADING_DIAGNOSTIC:
                self.machine.transition(AppState.IDLE, "Diagnostic cancelled")
            self._update_controls_for_idle()
            return
        self._stop_phase2_pipeline()
        summary = self._sample_rate_summary()
        if summary:
            self.append(f"RUN sample-rate benchmark final: {summary}")
        self.smith_chart.set_demo_mode(self.demo_mode_check.isChecked())
        if self.machine.state == AppState.RUN:
            self.machine.transition(AppState.IDLE, "User abort")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.abort_btn.setEnabled(False)
        self.demo_mode_check.setEnabled(True)
        self.run_profile.setEnabled(True)
        demo_mode = self.demo_mode_check.isChecked()
        self.log1_btn.setEnabled(demo_mode or self.serial.connected)
        self.log2_btn.setEnabled((not demo_mode) and self.serial.connected)
        self.log3_btn.setEnabled((not demo_mode) and self.serial.connected)
        # Enable diagnostic buttons after abort
        if self.serial.connected:
            self.diagnostic_btn.setEnabled(True)
            self.backup_btn.setEnabled(True)
            self.tlog_btn.setEnabled(True)
            self.adv_diag_btn.setEnabled(True)
            self.button_a.setEnabled(True)
            self.button_b.setEnabled(True)
        self.smith_chart.show_contour(self.smith_chart.contour_check.isChecked())
        self._update_controls_for_idle()
        self.append("Run aborted safely")

    def _start_phase2_pipeline(self, demo_mode: bool, mode: str = "log1"):
        if self._worker and self._worker.isRunning():
            self._worker.stop_polling()
        if self._controller:
            self._controller.close()
        profile = RUN_PROFILE_CONFIGS.get(self._run_profile_name, RUN_PROFILE_CONFIGS["Baseline"])
        raw_flush_every_rows = int(profile["raw_flush_every_rows"])
        raw_flush_interval_s = float(profile["raw_flush_interval_s"])
        logs_dir = self.log_file.parent
        self._controller = DataController(
            logs_dir=logs_dir,
            product=self.detected_product,
            serial_number=self.detected_serial_number,
            firmware=self.detected_firmware,
            raw_flush_every_rows=raw_flush_every_rows,
            raw_flush_interval_s=raw_flush_interval_s,
        )
        poll_interval_ms = int(profile["poll_interval_ms"]) if not demo_mode else 120
        command_timeout = float(profile["command_timeout_s"]) if not demo_mode else 0.8
        if mode == "log2":
            command_timeout = max(command_timeout, 0.25)
        if mode == "log3":
            poll_interval_ms = 20
            command_timeout = max(command_timeout, 0.1)
        self._worker = SerialWorker(
            self.serial,
            poll_interval_ms=poll_interval_ms,
            demo_mode=demo_mode,
            command_timeout=command_timeout,
            acquisition_mode=mode,
        )
        self._worker.sample_ready.connect(self._on_sample_ready)
        self._worker.worker_error.connect(self._on_worker_error)
        self._worker.start_polling()
        self._chart_timer.start()

    def _switch_to_high_speed(self) -> bool:
        current_baud = self._connected_baudrate()
        if current_baud == HIGH_SPEED_BAUD:
            self._active_baud = HIGH_SPEED_BAUD
            ver_result = self._query_ver_with_retry()
            if not ver_result.ok or not self._is_valid_ver_response(ver_result.response):
                self.machine.transition(AppState.ERROR, ver_result.message)
                self.append(f"High-speed validation failed: {ver_result.message}")
                return False
            self.append("Already at 230400 baud and communication verified")
            return True
        self.append(f"Switching unit baud to 230400 via '{HIGH_SPEED_BAUD_COMMAND}'")
        baud_result = self.serial.send_command(HIGH_SPEED_BAUD_COMMAND, timeout=HANDSHAKE_TIMEOUT_S)
        if not baud_result.ok:
            self.machine.transition(AppState.ERROR, baud_result.message)
            self.append(f"Failed to issue {HIGH_SPEED_BAUD_COMMAND}: {baud_result.message}")
            return False
        if self._is_invalid_command_response(baud_result.response):
            message = f"EVC rejected {HIGH_SPEED_BAUD_COMMAND} (Invalid Command)"
            self.machine.transition(AppState.ERROR, message)
            self.append(message)
            return False
        time.sleep(POST_SWITCH_SETTLE_S)
        self.serial.disconnect()
        self._update_usb_state_label()
        reconnect = self.serial.connect(self.port.currentText(), HIGH_SPEED_BAUD, timeout=HANDSHAKE_TIMEOUT_S)
        self.append(reconnect.message)
        self._update_usb_state_label()
        if not reconnect.ok:
            self.machine.transition(AppState.ERROR, reconnect.message)
            return False
        ver_result = self._query_ver_with_retry()
        if not ver_result.ok or not self._is_valid_ver_response(ver_result.response):
            self.machine.transition(AppState.ERROR, ver_result.message)
            self.append(f"Post-switch ver failed: {ver_result.message}")
            return False
        self._active_baud = HIGH_SPEED_BAUD
        self.baud.setCurrentText(str(HIGH_SPEED_BAUD))
        self.append(f"High-speed ver response:\n{ver_result.response}")
        return True

    def _switch_to_low_speed(self, fail_on_error: bool) -> bool:
        current_baud = self._connected_baudrate()
        if current_baud == LOW_SPEED_BAUD:
            self._active_baud = LOW_SPEED_BAUD
            ver_result = self._query_ver_with_retry()
            if not ver_result.ok or not self._is_valid_ver_response(ver_result.response):
                if fail_on_error:
                    self.machine.transition(AppState.ERROR, ver_result.message)
                self.append(f"Low-speed validation failed: {ver_result.message}")
                return False
            self.append("Already at 57600 baud and communication verified")
            return True

        switch_command = None
        switch_error = ""
        for command in (LOW_SPEED_BAUD_COMMAND, LOW_SPEED_BAUD_COMMAND_FALLBACK):
            self.append(f"Switching unit baud to 57600 via '{command}'")
            baud_result = self.serial.send_command(command, timeout=HANDSHAKE_TIMEOUT_S)
            if not baud_result.ok:
                switch_error = baud_result.message
                self.append(f"Failed to issue {command}: {baud_result.message}")
                continue
            if self._is_invalid_command_response(baud_result.response):
                switch_error = f"EVC rejected {command} (Invalid Command)"
                self.append(switch_error)
                continue
            switch_command = command
            break
        if not switch_command:
            if fail_on_error:
                self.machine.transition(AppState.ERROR, switch_error or "Unable to issue low-speed baud command")
            return False

        time.sleep(POST_SWITCH_SETTLE_S)
        self.serial.disconnect()
        self._update_usb_state_label()
        reconnect = self.serial.connect(self.port.currentText(), LOW_SPEED_BAUD, timeout=HANDSHAKE_TIMEOUT_S)
        self.append(reconnect.message)
        self._update_usb_state_label()
        if not reconnect.ok:
            if fail_on_error:
                self.machine.transition(AppState.ERROR, reconnect.message)
            return False

        ver_result = self._query_ver_with_retry()
        if not ver_result.ok or not self._is_valid_ver_response(ver_result.response):
            if fail_on_error:
                self.machine.transition(AppState.ERROR, ver_result.message)
            self.append(f"Post-switch low-speed ver failed: {ver_result.message}")
            return False

        self._active_baud = LOW_SPEED_BAUD
        self.baud.setCurrentText(str(LOW_SPEED_BAUD))
        self.append(f"Low-speed ver response:\n{ver_result.response}")
        return True

    def _restore_low_speed_on_close(self) -> bool:
        if not self.serial.connected:
            return True
        port = self.port.currentText().strip()
        if not port:
            return False

        candidates: list[int] = []
        current_baud = self._connected_baudrate()
        if current_baud:
            candidates.append(current_baud)
        candidates.extend([HIGH_SPEED_BAUD, LOW_SPEED_BAUD])
        tried: list[int] = []
        for baud in candidates:
            if baud in tried:
                continue
            tried.append(baud)
            if self._connected_baudrate() != baud:
                self.serial.disconnect()
                reconnect = self.serial.connect(port, baud, timeout=HANDSHAKE_TIMEOUT_S)
                if not reconnect.ok:
                    continue
            for command in (LOW_SPEED_BAUD_COMMAND, LOW_SPEED_BAUD_COMMAND_FALLBACK):
                switch_result = self.serial.send_command(command, timeout=HANDSHAKE_TIMEOUT_S)
                if not switch_result.ok:
                    continue
                if self._is_invalid_command_response(switch_result.response):
                    continue
                time.sleep(POST_SWITCH_SETTLE_S)
                self.serial.disconnect()
                reconnect_low = self.serial.connect(port, LOW_SPEED_BAUD, timeout=HANDSHAKE_TIMEOUT_S)
                if not reconnect_low.ok:
                    continue
                ver_result = self._query_ver_with_retry()
                if not ver_result.ok or not self._is_valid_ver_response(ver_result.response):
                    continue
                self._active_baud = LOW_SPEED_BAUD
                self.baud.setCurrentText(str(LOW_SPEED_BAUD))
                self.append(f"Restored unit baud to 57600 for app exit via '{command}'")
                return True
        return False

    def _query_ver_with_retry(self):
        last_result = None
        for _ in range(VER_RETRY_COUNT):
            result = self.serial.send_command("ver", timeout=HANDSHAKE_TIMEOUT_S)
            if result.ok:
                return result
            last_result = result
            time.sleep(0.1)
        return last_result

    def _query_scan_identity(self, setup_device_log: bool, fail_on_error: bool) -> bool:
        ver_result = None
        for _ in range(SCAN_VER_RETRY_COUNT):
            result = self.serial.send_command("ver", timeout=SCAN_COMMAND_TIMEOUT_S)
            ver_result = result
            if result.ok and self._is_valid_ver_response(result.response):
                break
            time.sleep(0.05)
        if ver_result is None or not ver_result.ok:
            if fail_on_error:
                self.machine.transition(AppState.ERROR, ver_result.message if ver_result else "No ver response")
            self.append(ver_result.message if ver_result else "No ver response")
            return False
        self.append(f"ver response:\n{ver_result.response}")
        if not self._is_valid_ver_response(ver_result.response):
            message = "Invalid ver response content (likely baud mismatch)"
            if fail_on_error:
                self.machine.transition(AppState.ERROR, message)
            self.append(message)
            return False
        product = self._extract_product_type(ver_result.response)
        if product:
            self.detected_product = product
            self.product_value.setText(product)
            self.append(f"Detected product type: {product}")
        firmware = self._extract_firmware(ver_result.response)
        if firmware:
            self.detected_firmware = firmware
            self.append(f"Detected firmware: {firmware}")
        if not product and not firmware:
            message = "Invalid ver response content"
            if fail_on_error:
                self.machine.transition(AppState.ERROR, message)
            self.append(message)
            return False

        sn_result = self.serial.send_command("sn", timeout=SCAN_COMMAND_TIMEOUT_S)
        if not sn_result.ok:
            if fail_on_error:
                self.machine.transition(AppState.ERROR, sn_result.message)
            self.append(sn_result.message)
            return False
        self.append(f"sn response:\n{sn_result.response}")
        serial_number = self._extract_unit_serial(sn_result.response)
        if serial_number:
            self.detected_serial_number = serial_number
            self.serial_number_value.setText(serial_number)
            if product:
                product_name = self._resolve_product_name(product, serial_number)
                self.detected_product = product_name
                self.product_value.setText(product_name)
                self.append(f"Detected product type: {product_name}")
            if setup_device_log and not self._device_log_ready:
                self.log_file = configure_logging(f"evc_gui_{serial_number}")
                self._device_log_ready = True
                self.append(f"Logging switched to {self.log_file.name}")
        else:
            message = "Invalid sn response content"
            if fail_on_error:
                self.machine.transition(AppState.ERROR, message)
            self.append(message)
            return False
        return True

    def _build_baud_scan_candidates(self) -> list[int]:
        candidates: list[int] = []
        ordered: list[int] = []
        try:
            ordered.append(int(self.baud.currentText()))
        except ValueError:
            pass
        ordered.extend(START_BAUD_CANDIDATES)
        for i in range(self.baud.count()):
            try:
                ordered.append(int(self.baud.itemText(i)))
            except ValueError:
                continue
        for baud in ordered:
            if baud not in candidates:
                candidates.append(baud)
        return candidates

    @staticmethod
    def _is_prompt_only_line(line: str) -> bool:
        return line.endswith(">") and " " not in line

    def _is_valid_ver_response(self, response: str) -> bool:
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        payload_lines = [line for line in lines if not self._is_prompt_only_line(line)]
        if not payload_lines:
            return False
        if any("�" in line for line in payload_lines):
            return False
        if not any(line.lower() == "ver" for line in payload_lines):
            return False
        info_lines = [line for line in payload_lines if line.lower() != "ver"]
        if any("evc" in line.lower() and "version" in line.lower() for line in info_lines):
            return True
        return bool(self._extract_product_type(response) or self._extract_firmware(response))

    def _stop_phase2_pipeline(self):
        self._chart_timer.stop()
        if self._worker:
            try:
                self._worker.sample_ready.disconnect(self._on_sample_ready)
            except (RuntimeError, TypeError):
                pass
            try:
                self._worker.worker_error.disconnect(self._on_worker_error)
            except (RuntimeError, TypeError):
                pass
            self._worker.stop_polling()
            self._worker = None
        if self._controller:
            self._controller.close()
            self._controller = None

    @Slot(object, str, str)
    def _on_sample_ready(self, sample, pdat_line: str, psum_line: str):
        if not self._controller:
            return
        self._record_sample_rate_benchmark()
        self._controller.append_sample(sample, pdat_line, psum_line)
        self._run_ui_sample_counter += 1
        if (self._run_ui_sample_counter % max(1, self._run_ui_update_stride)) != 0:
            return
        if self.demo_mode_check.isChecked():
            self.smith_chart.append_demo_point()
        else:
            if self._is_quantum_family():
                self.smith_chart.update_dual_impedance(sample.rs, sample.xs, sample.lf_rs, sample.lf_xs)
            else:
                self.smith_chart.update_impedance(sample.rs, sample.xs)
        self.power_scope.update_latest(sample)

    @Slot(str)
    def _on_worker_error(self, message: str):
        self.append(f"Phase 2 worker: {message}")

    @Slot(bool)
    def _on_demo_mode_toggled(self, enabled: bool):
        self.smith_chart.set_demo_mode(enabled)
        self._update_controls_for_idle()
    
    @Slot(bool)
    def _on_contour_toggled(self, enabled: bool):
        """Handle contour checkbox toggle to load and plot Z-parameters."""
        if not enabled:
            self.smith_chart.show_contour(False)
            return

        if self.machine.state == AppState.RUN:
            self.smith_chart.show_contour(True)
            return

        if self.machine.state == AppState.DOWNLOADING_CONTOUR:
            return

        if self.smith_chart._contour_cache:
            self.smith_chart.show_contour(True)
            return

        if self.demo_mode_check.isChecked():
            self.append("Demo mode can only show cached contour data; load contour on a real device first.")
            self.smith_chart.contour_check.setChecked(False)
            return

        if not self.serial.connected:
            self.append("Connect to device first to plot contour")
            self.smith_chart.contour_check.setChecked(False)
            return

        if not self._switch_to_high_speed():
            self.append("Cannot download contour: failed to switch to 230400 baud")
            self.smith_chart.contour_check.setChecked(False)
            return

        if not self.machine.transition(AppState.DOWNLOADING_CONTOUR, "Downloading contour data"):
            return
        self.state_label.setText(AppState.DOWNLOADING_CONTOUR.name)
        QApplication.processEvents()
        self._load_and_plot_contour(show_after_load=True)

    def _auto_download_contour_after_scan(self):
        if self.demo_mode_check.isChecked():
            return
        if not self.serial.connected:
            return
        if not self._switch_to_high_speed():
            self.append("Skipping auto contour download: unable to switch to 230400 baud")
            return
        if self.smith_chart._contour_cache:
            return
        if not self.machine.transition(AppState.DOWNLOADING_CONTOUR, "Auto contour download after scan"):
            return
        self.state_label.setText(AppState.DOWNLOADING_CONTOUR.name)
        QApplication.processEvents()
        self.append("Auto-downloading contour Z-parameters after equipment scan...")
        self._load_and_plot_contour(show_after_load=self.smith_chart.contour_check.isChecked())

    def _update_controls_for_idle(self):
        self._update_usb_state_label()
        demo_mode = self.demo_mode_check.isChecked()
        if self.machine.state == AppState.RUN:
            return
        if self.machine.state == AppState.DOWNLOADING_CONTOUR:
            self.log1_btn.setEnabled(False)
            self.log2_btn.setEnabled(False)
            self.log3_btn.setEnabled(False)
            self.probe_btn.setEnabled(False)
            return
        if self.machine.state == AppState.DOWNLOADING_DIAGNOSTIC:
            self.start_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.port.setEnabled(False)
            self.baud.setEnabled(False)
            self.run_profile.setEnabled(False)
            self.demo_mode_check.setEnabled(False)
            self.log1_btn.setEnabled(False)
            self.log2_btn.setEnabled(False)
            self.log3_btn.setEnabled(False)
            self.probe_btn.setEnabled(False)
            self.diagnostic_btn.setEnabled(False)
            self.backup_btn.setEnabled(False)
            self.tlog_btn.setEnabled(False)
            self.adv_diag_btn.setEnabled(False)
            self.button_a.setEnabled(False)
            self.button_b.setEnabled(False)
            return
        connected = self.serial.connected
        self.log1_btn.setEnabled(demo_mode or connected)
        self.log2_btn.setEnabled((not demo_mode) and connected)
        self.log3_btn.setEnabled((not demo_mode) and connected)
        self.probe_btn.setEnabled(self.serial.connected and not demo_mode)
        self.run_profile.setEnabled(True)
        # Enable diagnostic buttons when connected
        self.diagnostic_btn.setEnabled(connected)
        self.backup_btn.setEnabled(connected)
        self.tlog_btn.setEnabled(connected)
        self.adv_diag_btn.setEnabled(connected)
        self.button_a.setEnabled(connected)
        self.button_b.setEnabled(connected)
    
    def _cap_grid_limits(self) -> tuple[int, int]:
        """Return (max_coarse, max_fine) for the connected product family."""
        if self._is_chronos_family() and self._is_chronos_legacy_unit():
            return 12, 12
        return 6, 63

    def _is_chronos_family(self) -> bool:
        product = (self.detected_product or "").strip().lower()
        return product.startswith("chronos")

    def _resolve_product_name(self, product: str, serial_number: str) -> str:
        if product.strip().lower() != "chronos":
            return product
        prefix = self._serial_prefix(serial_number)
        if prefix is None:
            return "Chronos"
        if 191 <= prefix <= 195:
            return "Chronos 1"
        if prefix >= 196:
            return "Chronos 2.0"
        return "Chronos"

    def _is_quantum_family(self) -> bool:
        product = (self.detected_product or "").strip().lower()
        return product.startswith("quantum")

    @staticmethod
    def _serial_prefix(serial_number: str) -> int | None:
        serial_digits = "".join(ch for ch in serial_number if ch.isdigit())
        if len(serial_digits) < 3:
            return None
        try:
            return int(serial_digits[:3])
        except ValueError:
            return None

    def _is_chronos_legacy_unit(self) -> bool:
        prefix = self._serial_prefix(self.detected_serial_number)
        if prefix is None:
            return False
        return 191 <= prefix <= 195

    def _pct_to_cap_position(self, pct: int) -> int:
        """Convert percentage to the actual linear capacitor position index."""
        max_coarse, max_fine = self._cap_grid_limits()
        min_pos = 0
        max_pos = (max_coarse + 1) * (max_fine + 1) - 1
        return max(min_pos, min(max_pos, int(round((pct / 100.0) * max_pos))))

    def _cap_position_to_coarse_fine(self, position: int) -> tuple[int, int]:
        """Map a linear position index to (coarse, fine) using product-specific ranges."""
        max_coarse, max_fine = self._cap_grid_limits()
        fine_span = max_fine + 1
        max_pos = (max_coarse + 1) * fine_span - 1
        position = max(0, min(position, max_pos))
        coarse, fine = divmod(position, fine_span)
        return min(coarse, max_coarse), min(fine, max_fine)

    def _load_and_plot_contour(self, show_after_load: bool = True):
        """Download contour data once, cache it, then plot from cache."""
        if self.smith_chart._contour_cache:
            self.smith_chart.show_contour(show_after_load)
            self.append("Contour cache already loaded; plotting from cached data.")
            return

        self.append("Loading Z-parameters for contour plot (edge positions)...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.setEnabled(False)
        self.state_label.setText(AppState.DOWNLOADING_CONTOUR.name)
        
        # Show progress bar with indeterminate animation
        self.progress.setRange(0, 0)
        self.progress.show()

        try:
            z_params_list = []
            contour_rows = []

            max_coarse, max_fine = self._cap_grid_limits()
            max_position = (max_coarse + 1) * (max_fine + 1) - 1

            # Sample at 2% increments in the product-specific capacitance space.
            percentages = list(range(0, 101, 2))

            zpar_bands = ["f1"]
            if self._is_quantum_family():
                zpar_bands = ["hf", "lf"]
            self.append(f"Querying {'/'.join(zpar_bands)} band edge positions...")
            
            # Calculate total queries for progress tracking
            total_queries = len(zpar_bands) * 4 * len(percentages)
            current_query = 0
            self.progress.setRange(0, total_queries)

            for band in zpar_bands:
                for line_name, fixed_c1, fixed_c2, reverse in [
                    ("Line 1", 0, None, False),
                    ("Line 2", None, max_position, False),
                    ("Line 3", max_position, None, True),
                    ("Line 4", None, 0, True),
                ]:
                    line_percentages = list(reversed(percentages)) if reverse else percentages
                    for pct in line_percentages:
                        pos = self._pct_to_cap_position(pct)
                        c1_position = pos if fixed_c1 is None else fixed_c1
                        c2_position = pos if fixed_c2 is None else fixed_c2
                        c1_coarse, c1_fine = self._cap_position_to_coarse_fine(c1_position)
                        c2_coarse, c2_fine = self._cap_position_to_coarse_fine(c2_position)
                        cmd = f"zpar show {band} {c1_coarse} {c1_fine} {c2_coarse} {c2_fine}"
                        z_params = self._query_and_parse_zpar(cmd)
                        
                        if not z_params:
                            continue

                        z_params_list.append(z_params)
                        load_r, load_x = calculate_load_impedance_from_z_params(z_params)
                        gamma = impedance_to_gamma(load_r, load_x)
                        contour_rows.append(
                            {
                                "band": band.upper(),
                                "line": line_name,
                                "pct": pct,
                                "c1_coarse": c1_coarse,
                                "c1_fine": c1_fine,
                                "c2_coarse": c2_coarse,
                                "c2_fine": c2_fine,
                                "cmd": cmd,
                                "z11_r": z_params.z11_r,
                                "z11_i": z_params.z11_i,
                                "z21_r": z_params.z21_r,
                                "z21_i": z_params.z21_i,
                                "z12_r": z_params.z12_r,
                                "z12_i": z_params.z12_i,
                                "z22_r": z_params.z22_r,
                                "z22_i": z_params.z22_i,
                                "s22_r": z_params.z22_r,
                                "s22_i": z_params.z22_i,
                                "s22_mag": abs(complex(z_params.z22_r, z_params.z22_i)),
                                "s22_phase_deg": math.degrees(cmath.phase(complex(z_params.z22_r, z_params.z22_i))),
                                "z_load_r": load_r,
                                "z_load_x": load_x,
                                "gamma_real": gamma.real,
                                "gamma_imag": gamma.imag,
                                "gamma_mag": abs(gamma),
                                "gamma_phase_deg": math.degrees(cmath.phase(gamma)),
                            }
                        )
                        
                        # Update progress bar every 10 queries to avoid blocking serial communication
                        current_query += 1
                        if current_query % 10 == 0:
                            self.progress.setValue(current_query)
                            QApplication.processEvents()
                        
                        if line_name == "Line 3":
                            self.append(
                                f"{band.upper()} {line_name} pct={pct:>3}% -> C1=({c1_coarse},{c1_fine}), C2=({c2_coarse},{c2_fine}) | "
                                f"Z=({load_r:.3f},{load_x:.3f}) | gamma=({gamma.real:.4f},{gamma.imag:.4f}) | |gamma|={abs(gamma):.4f}"
                            )

            if contour_rows:
                export_path = self._export_contour_csv(contour_rows)
                self.append(f"Contour CSV exported: {export_path}")
                self.append(f"Loaded {len(z_params_list)} Z-parameter edge points for contour")
                groups = {}
                for row in contour_rows:
                    key = f"{row.get('band', 'F1')} {row['line']}" if self._is_quantum_family() else row["line"]
                    groups.setdefault(key, []).append(row)
                contour_cache = {}
                self.smith_chart.plot_z_parameter_contour([], clear=True)
                for line_name, line_rows in groups.items():
                    line_z_params = []
                    for row in line_rows:
                        line_z_params.append(
                            ZParameters(
                                z11_r=row["z11_r"],
                                z11_i=row["z11_i"],
                                z21_r=row["z21_r"],
                                z21_i=row["z21_i"],
                                z12_r=row["z12_r"],
                                z12_i=row["z12_i"],
                                z22_r=row["z22_r"],
                                z22_i=row["z22_i"],
                            )
                        )
                    contour_cache[line_name] = line_z_params
                    if line_z_params:
                        color = None
                        if line_name.lower().startswith("hf "):
                            color = QColor("#FF2020")
                        elif line_name.lower().startswith("lf "):
                            color = QColor("#007BFF")
                        self.smith_chart.plot_z_parameter_contour(line_z_params, clear=False, color=color)
                self.smith_chart.set_contour_cache(contour_cache)
                self.smith_chart.show_contour(show_after_load)
            else:
                self.append("No Z-parameters loaded - contour plot failed")
                self.smith_chart.contour_check.setChecked(False)
        finally:
            QApplication.restoreOverrideCursor()
            self.setEnabled(True)
            self.progress.hide()  # Hide progress bar after download completes
            self.progress.setRange(0, 100)  # Reset to normal range
            self.progress.setValue(0)  # Reset progress value
            if self.machine.state == AppState.DOWNLOADING_CONTOUR:
                self.machine.transition(AppState.IDLE, "Contour download complete")

    def _export_contour_csv(self, contour_rows: list[dict]) -> Path:
        """Export contour lines to CSV for external plotting in Excel or Python."""
        export_dir = self.log_file.parent if self.log_file else Path.cwd()
        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = export_dir / f"contour_export_{self.detected_serial_number or 'demo'}_{len(contour_rows)}pts.csv"

        fieldnames = [
            "band",
            "line",
            "pct",
            "c1_coarse",
            "c1_fine",
            "c2_coarse",
            "c2_fine",
            "cmd",
            "z11_r",
            "z11_i",
            "z21_r",
            "z21_i",
            "z12_r",
            "z12_i",
            "z22_r",
            "z22_i",
            "s22_r",
            "s22_i",
            "s22_mag",
            "s22_phase_deg",
            "z_load_r",
            "z_load_x",
            "gamma_real",
            "gamma_imag",
            "gamma_mag",
            "gamma_phase_deg",
        ]

        with file_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in contour_rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

        return file_path
    
    def _query_and_parse_zpar(self, cmd: str) -> ZParameters | None:
        """Query device for Z-parameter and parse response."""
        try:
            result = self.serial.send_command(
                cmd,
                timeout=ZPAR_COMMAND_TIMEOUT_S,
                read_timeout=ZPAR_READ_TIMEOUT_S,
                payload_quiet_period_s=ZPAR_PAYLOAD_QUIET_S,
            )
            if result.ok:
                parsed = self._parse_zpar_response(result.response)
                if parsed:
                    return parsed
            # Fallback to the original command strategy if the fast path fails.
            fallback = self.serial.send_command(cmd)
            if not fallback.ok:
                return None
            return self._parse_zpar_response(fallback.response)
        except Exception:
            return None
    
    @staticmethod
    def _parse_zpar_response(response: str) -> ZParameters | None:
        """
        Parse 'zpar show' response to extract Z-parameters.
        Response format:
        (C1: x, f1) (C2: x, f2)   Z11 = (r, i)  Z21 = (r, i)  Z12 = (r, i)  Z22 = (r, i)
        """
        import re
        
        number = r"([+-]?\d+(?:\.\d+)?)"
        try:
            z11_match = re.search(rf"Z11\s*=\s*\(\s*{number}\s*,\s*{number}\s*\)", response, re.IGNORECASE)
            z21_match = re.search(rf"Z21\s*=\s*\(\s*{number}\s*,\s*{number}\s*\)", response, re.IGNORECASE)
            z12_match = re.search(rf"Z12\s*=\s*\(\s*{number}\s*,\s*{number}\s*\)", response, re.IGNORECASE)
            z22_match = re.search(rf"Z22\s*=\s*\(\s*{number}\s*,\s*{number}\s*\)", response, re.IGNORECASE)
            
            if all([z11_match, z21_match, z12_match, z22_match]):
                return ZParameters(
                    z11_r=float(z11_match.group(1)),
                    z11_i=float(z11_match.group(2)),
                    z21_r=float(z21_match.group(1)),
                    z21_i=float(z21_match.group(2)),
                    z12_r=float(z12_match.group(1)),
                    z12_i=float(z12_match.group(2)),
                    z22_r=float(z22_match.group(1)),
                    z22_i=float(z22_match.group(2)),
                )
        except (ValueError, AttributeError):
            pass
        
        return None

    def _refresh_scope(self):
        if not self._controller:
            return
        samples = self._controller.window(self.power_scope.selected_seconds())
        self.power_scope.update_chart(samples)
        self.power_scope.update_latest(self._controller.latest())

    @Slot(object, object, str)
    def on_state_changed(self, source, target, reason):
        self.state_label.setText(target.name)
        self._update_usb_state_label()
        self.append(f"{source.name} -> {target.name}: {reason}")

    def closeEvent(self, event):
        try:
            self._save_result_text()
            self._stop_phase2_pipeline()
            self._cancel_diagnostic_job()
            if self.machine.state not in (AppState.IDLE, AppState.ERROR, AppState.CLEANUP, AppState.EXIT):
                self.machine.transition(AppState.IDLE, "Close requested")
            if self.machine.state in (AppState.IDLE, AppState.ERROR):
                self.machine.transition(AppState.CLEANUP, "Application closing")
            if self.serial.connected:
                if not self._restore_low_speed_on_close():
                    self.append("Warning: Could not confirm baud restore to 57600 before exit")
            self.serial.disconnect()
            self._update_usb_state_label()
            if self.machine.state == AppState.CLEANUP:
                self.machine.transition(AppState.EXIT, "Cleanup complete")
            event.accept()
        except Exception:
            log.exception("Unhandled error during close")
            event.accept()

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

    @staticmethod
    def _extract_firmware(response: str) -> str:
        for line in response.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "version" in stripped.lower() or "fw" in stripped.lower():
                return stripped
        return ""
