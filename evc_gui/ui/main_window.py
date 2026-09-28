import csv
import cmath
import logging
import math
import time
from pathlib import Path
import re

from PySide6.QtCore import Qt, QTimer, Slot, Signal, QObject
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
START_BAUD_CANDIDATES = (57600, 230400)
HIGH_SPEED_BAUD = 230400
RUN_COMMAND_TIMEOUT_S = 0.075
HANDSHAKE_TIMEOUT_S = 1.0
SCAN_COMMAND_TIMEOUT_S = 0.5
POST_SWITCH_SETTLE_S = 0.35
VER_RETRY_COUNT = 3
SCAN_VER_RETRY_COUNT = 3


# Signal emitter for thread-safe scanning completion
class ScanCompleteSignals(QObject):
    scan_complete = Signal(list)  # Emits list of DetectedDevice


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
        self._active_baud = 57600
        self._device_log_ready = False
        self._worker: SerialWorker | None = None
        self._controller: DataController | None = None
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
        self.baud.setCurrentText("57600")
        self.serial_number_value = QLabel("-")
        self.refresh_btn = QPushButton("Refresh Ports")
        self.start_btn = QPushButton("Start / Connect")
        self.demo_mode_check = QCheckBox("Demo Mode (Phase 2/3)")
        self.probe_btn = QPushButton("Probe")
        self.run_btn = QPushButton("Run")
        self.abort_btn = QPushButton("Abort")
        self.exit_btn = QPushButton("Exit")
        self.probe_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.abort_btn.setEnabled(False)
        widgets = [
            ("Detected Product", self.product_value),
            ("Detected Unit S/N", self.serial_number_value),
            ("COM Port", self.port),
            ("Baud", self.baud),
        ]
        for row, (text, widget) in enumerate(widgets):
            form.addWidget(QLabel(text), row, 0)
            form.addWidget(widget, row, 1)
        form.addWidget(self.refresh_btn, 4, 0, 1, 2)
        form.addWidget(self.start_btn, 5, 0, 1, 2)
        form.addWidget(self.demo_mode_check, 6, 0, 1, 2)
        form.addWidget(self.probe_btn, 7, 0, 1, 2)
        form.addWidget(self.run_btn, 8, 0, 1, 2)
        form.addWidget(self.abort_btn, 9, 0, 1, 2)
        form.addWidget(self.exit_btn, 10, 0, 1, 2)
        self.state_label = QLabel("INITIALIZATION")
        self.state_label.setObjectName("state")
        form.addWidget(QLabel("State"), 11, 0)
        form.addWidget(self.state_label, 11, 1)
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
        form.addWidget(self.progress, 12, 0, 1, 2)
        form.setRowStretch(13, 1)
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
        for name, note in [("Future", "Phase 4 extension area")]:
            page = QWidget()
            lay = QVBoxLayout(page)
            label = QLabel(note)
            label.setAlignment(Qt.AlignCenter)
            lay.addWidget(label)
            tabs.addTab(page, name)

        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.start_btn.clicked.connect(self.start_connection)
        self.demo_mode_check.toggled.connect(self._on_demo_mode_toggled)
        self.smith_chart.contour_check.toggled.connect(self._on_contour_toggled)
        self.probe_btn.clicked.connect(self.probe)
        self.run_btn.clicked.connect(self.run_monitoring)
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
        if not result.ok:
            self.machine.transition(AppState.ERROR, f"Connection failed: {result.message}")
            self.start_btn.setEnabled(True)
            self._update_controls_for_idle()
            return
        
        # Validate identity
        if not self._query_scan_identity(setup_device_log=False, fail_on_error=False):
            self.append("Identity validation failed")
            self.serial.disconnect()
            self.machine.transition(AppState.ERROR, "Identity validation failed")
            self.start_btn.setEnabled(True)
            self._update_controls_for_idle()
            return
        
        self.append(f"Handshake OK at {device.baudrate} baud")
        self._active_baud = device.baudrate
        self.port.setCurrentText(device.port)
        self.baud.setCurrentText(str(device.baudrate))
        
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

    def run_monitoring(self):
        demo_mode = self.demo_mode_check.isChecked()
        self.smith_chart.reset_points()
        self.smith_chart.set_demo_mode(demo_mode)
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
            if not self._query_scan_identity(setup_device_log=True, fail_on_error=True):
                return
            if not self._switch_to_high_speed():
                return

        self.machine.transition(AppState.CHECK_CONNECTION, "Validate existing connection")
        self.machine.transition(AppState.GETTING_START, "Prepare monitoring")
        self.machine.transition(AppState.RUN, "Phase 2 data acquisition run")
        self.progress.setRange(0, 0)
        self.abort_btn.setEnabled(True)
        self.run_btn.setEnabled(False)
        self.probe_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.demo_mode_check.setEnabled(False)
        if self.smith_chart.contour_check.isChecked():
            self.smith_chart.show_contour(True)
        self._start_phase2_pipeline(demo_mode=demo_mode)
        if demo_mode:
            self.append("RUN entered. Feeding demo data into Power Scope.")
        else:
            self.append("RUN entered. Querying pdat1 + psum1 and updating Power Scope.")

    def abort(self):
        self._stop_phase2_pipeline()
        self.smith_chart.set_demo_mode(self.demo_mode_check.isChecked())
        if self.machine.state == AppState.RUN:
            self.machine.transition(AppState.IDLE, "User abort")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.abort_btn.setEnabled(False)
        self.demo_mode_check.setEnabled(True)
        self.smith_chart.show_contour(self.smith_chart.contour_check.isChecked())
        self._update_controls_for_idle()
        self.append("Run aborted safely")

    def _start_phase2_pipeline(self, demo_mode: bool):
        if self._worker and self._worker.isRunning():
            self._worker.stop_polling()
        if self._controller:
            self._controller.close()
        logs_dir = self.log_file.parent
        self._controller = DataController(
            logs_dir=logs_dir,
            product=self.detected_product,
            serial_number=self.detected_serial_number,
            firmware=self.detected_firmware,
        )
        command_timeout = RUN_COMMAND_TIMEOUT_S if not demo_mode else 0.8
        self._worker = SerialWorker(self.serial, demo_mode=demo_mode, command_timeout=command_timeout)
        self._worker.sample_ready.connect(self._on_sample_ready)
        self._worker.worker_error.connect(self._on_worker_error)
        self._worker.start_polling()
        self._chart_timer.start()

    def _switch_to_high_speed(self) -> bool:
        if self._active_baud == HIGH_SPEED_BAUD:
            ver_result = self._query_ver_with_retry()
            if not ver_result.ok or not self._is_valid_ver_response(ver_result.response):
                self.machine.transition(AppState.ERROR, ver_result.message)
                self.append(f"High-speed validation failed: {ver_result.message}")
                return False
            self.append("Already at 230400 baud and communication verified")
            return True
        self.append("Switching unit baud to 230400 via 'baud 7'")
        baud_result = self.serial.send_command("baud 7", timeout=HANDSHAKE_TIMEOUT_S)
        if not baud_result.ok:
            self.machine.transition(AppState.ERROR, baud_result.message)
            self.append(f"Failed to issue baud 7: {baud_result.message}")
            return False
        time.sleep(POST_SWITCH_SETTLE_S)
        self.serial.disconnect()
        reconnect = self.serial.connect(self.port.currentText(), HIGH_SPEED_BAUD, timeout=HANDSHAKE_TIMEOUT_S)
        self.append(reconnect.message)
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
        self._controller.append_sample(sample, pdat_line, psum_line)
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
        if self.smith_chart._contour_cache:
            return
        if not self.machine.transition(AppState.DOWNLOADING_CONTOUR, "Auto contour download after scan"):
            return
        self.state_label.setText(AppState.DOWNLOADING_CONTOUR.name)
        QApplication.processEvents()
        self.append("Auto-downloading contour Z-parameters after equipment scan...")
        self._load_and_plot_contour(show_after_load=self.smith_chart.contour_check.isChecked())

    def _update_controls_for_idle(self):
        demo_mode = self.demo_mode_check.isChecked()
        if self.machine.state == AppState.RUN:
            return
        if self.machine.state == AppState.DOWNLOADING_CONTOUR:
            self.run_btn.setEnabled(False)
            self.probe_btn.setEnabled(False)
            return
        self.run_btn.setEnabled(demo_mode or self.serial.connected)
        self.probe_btn.setEnabled(self.serial.connected and not demo_mode)
    
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
            result = self.serial.send_command(cmd)
            if not result.ok:
                return None
            return self._parse_zpar_response(result.response)
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
        self.append(f"{source.name} -> {target.name}: {reason}")

    def closeEvent(self, event):
        try:
            self._stop_phase2_pipeline()
            if self.machine.state not in (AppState.IDLE, AppState.ERROR, AppState.CLEANUP, AppState.EXIT):
                self.machine.transition(AppState.IDLE, "Close requested")
            if self.machine.state in (AppState.IDLE, AppState.ERROR):
                self.machine.transition(AppState.CLEANUP, "Application closing")
            self.serial.disconnect()
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
