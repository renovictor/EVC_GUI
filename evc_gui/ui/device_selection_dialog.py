"""Device selection dialog for choosing detected EVC devices."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QMessageBox,
)

from evc_gui.services.port_scanner import DetectedDevice


class DeviceSelectionDialog(QDialog):
    """Dialog to display detected devices and allow user selection."""
    
    MANUAL_SELECTION = "MANUAL"
    
    def __init__(self, devices: list[DetectedDevice], parent=None):
        super().__init__(parent)
        self.devices = devices
        self.selected_device: Optional[DetectedDevice] = None
        self.use_manual: bool = False
        self.setWindowTitle("Select EVC Device")
        self.setMinimumWidth(950)  # Wider to accommodate expanded columns
        self.setMinimumHeight(450)
        self.setModal(True)
        # Apply dark theme styling to dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #0e1830;
                color: #eaf1ff;
            }
            QLabel {
                color: #eaf1ff;
            }
            QPushButton {
                background-color: #2463a8;
                border: none;
                border-radius: 6px;
                padding: 9px;
                color: #eaf1ff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #347dca;
            }
        """)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Detected EVC Devices")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffffff; margin-bottom: 10px;")
        layout.addWidget(header)
        
        # Info text
        info = QLabel(f"Found {len(self.devices)} device(s). Select one to connect:")
        info.setStyleSheet("font-size: 12px; color: #ffffff; margin-bottom: 8px;")
        layout.addWidget(info)
        
        # Table with detected devices
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "COM Port", "Product", "Serial Number", "Firmware", "Baud Rate"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        
        # Apply table styling for better visibility
        table_style = """
            QTableWidget {
                background-color: #172542;
                alternate-background-color: #1a2d4a;
                color: #000000;
                gridline-color: #47648f;
            }
            QTableWidget::item {
                padding: 4px;
                color: #000000;
            }
            QTableWidget::item:selected {
                background-color: #ff1493;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #253858;
                color: #ffffff;
                padding: 4px;
                border: none;
                font-weight: bold;
            }
        """
        self.table.setStyleSheet(table_style)
        
        for row, device in enumerate(self.devices):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(device.port))
            self.table.setItem(row, 1, QTableWidgetItem(device.product))
            self.table.setItem(row, 2, QTableWidgetItem(device.serial_number))
            self.table.setItem(row, 3, QTableWidgetItem(device.firmware))
            self.table.setItem(row, 4, QTableWidgetItem(str(device.baudrate)))
        
        # Auto-select first row if available
        if self.devices:
            self.table.selectRow(0)
        
        # Set column widths for better visibility
        self.table.setColumnWidth(0, 80)   # COM Port
        self.table.setColumnWidth(1, 100)  # Product
        self.table.setColumnWidth(2, 120)  # Serial Number
        self.table.setColumnWidth(3, 300)  # Firmware
        self.table.setColumnWidth(4, 90)   # Baud Rate
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        select_btn = QPushButton("Connect to Selected Device")
        select_btn.clicked.connect(self._on_select)
        button_layout.addWidget(select_btn)
        
        manual_btn = QPushButton("Use Manual Selection")
        manual_btn.setToolTip("Manually select COM port and baud rate")
        manual_btn.clicked.connect(self._on_manual)
        button_layout.addWidget(manual_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _on_select(self):
        """Handle device selection."""
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.devices):
            QMessageBox.warning(self, "No Selection", "Please select a device first.")
            return
        
        self.selected_device = self.devices[current_row]
        self.use_manual = False
        self.accept()
    
    def _on_manual(self):
        """Handle manual selection fallback."""
        self.selected_device = None
        self.use_manual = True
        self.accept()
    
    def get_selected_device(self) -> Optional[DetectedDevice]:
        """Get the selected device after dialog closes."""
        return self.selected_device

