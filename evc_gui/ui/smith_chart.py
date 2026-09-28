from __future__ import annotations

from collections import deque
import cmath
import math
import random
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QScatterSeries, QValueAxis


Z0_OHMS = 50.0


@dataclass
class ZParameters:
    z11_r: float
    z11_i: float
    z21_r: float
    z21_i: float
    z12_r: float
    z12_i: float
    z22_r: float
    z22_i: float


def impedance_to_gamma(load_r: float, load_x: float, z0: float = Z0_OHMS) -> complex:
    z = complex(load_r / z0, load_x / z0)
    denominator = z + 1
    if abs(denominator) < 1e-12:
        return complex(0.999, 0.0)
    return (z - 1) / denominator


def gamma_to_impedance(gamma: complex, z0: float = Z0_OHMS) -> tuple[float, float]:
    if abs(1 - gamma) < 1e-12:
        return 9999.0, 0.0
    z = z0 * ((1 + gamma) / (1 - gamma))
    return float(z.real), float(z.imag)


def calculate_load_impedance_from_z_params(z_params: ZParameters) -> tuple[float, float]:
    """
    Calculate load impedance using Z-parameters with formula:
    Z_L = -(Z12 * Z21) / (Z0 - Z11) - Z22
    where Z0 = 50 ohms
    """
    z11 = complex(z_params.z11_r, z_params.z11_i)
    z21 = complex(z_params.z21_r, z_params.z21_i)
    z12 = complex(z_params.z12_r, z_params.z12_i)
    z22 = complex(z_params.z22_r, z_params.z22_i)
    
    denominator = Z0_OHMS - z11
    if abs(denominator) < 1e-12:
        return 50.0, 0.0
    
    z_l = -(z12 * z21) / denominator - z22
    return float(z_l.real), float(z_l.imag)


class SmithChartView(QChartView):
    """Custom QChartView with tooltip support showing impedance on hover."""
    
    def __init__(self, chart):
        super().__init__(chart)
        self._chart = chart
        self.setMouseTracking(True)
    
    def mouseMoveEvent(self, event):
        """Show impedance tooltip when hovering over the chart."""
        super().mouseMoveEvent(event)
        
        try:
            scene_pos = self.mapToScene(event.pos())
            chart_pos = self._chart.mapFromScene(scene_pos)
            
            gamma = complex(chart_pos.x(), chart_pos.y())
            
            if abs(gamma) <= 1.01:
                load_r, load_x = gamma_to_impedance(gamma)
                mag = abs(gamma)
                phase_deg = math.degrees(cmath.phase(gamma))
                
                tooltip_text = (
                    f"Z = {load_r:.2f} + j{load_x:.2f} ohms\n"
                    f"|Gamma| = {mag:.3f}, angle = {phase_deg:.1f} deg"
                )
                self.setToolTip(tooltip_text)
            else:
                self.setToolTip("")
        except Exception:
            pass


class SmithChartWidget(QWidget):
    DEMO_PATTERNS = ["VSWR=5 Circle", "Spiral", "Linear", "Random"]
    
    contour_requested = Signal(str)  # Signal to request contour data from main window

    def __init__(self):
        super().__init__()
        self._gamma_points: deque[complex] = deque(maxlen=20)
        self._lf_gamma_points: deque[complex] = deque(maxlen=20)
        self._demo_step = 0
        self._active_r = 0.0
        self._active_x = 0.0
        self._contour_series = []
        self._contour_cache: dict[str, list[ZParameters]] = {}
        self._hover_label = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        value_box = QGroupBox("Impedance")
        value_grid = QGridLayout(value_box)
        self.load_r_edit = QLineEdit("0.00")
        self.load_x_edit = QLineEdit("0.00")
        self.load_r_edit.setReadOnly(True)
        self.load_x_edit.setReadOnly(True)
        value_grid.addWidget(QLabel("Load R (ohm)"), 0, 0)
        value_grid.addWidget(self.load_r_edit, 0, 1)
        value_grid.addWidget(QLabel("Load X (ohm)"), 1, 0)
        value_grid.addWidget(self.load_x_edit, 1, 1)
        top.addWidget(value_box, 0)

        demo_box = QGroupBox("Demo Pattern")
        demo_grid = QGridLayout(demo_box)
        self.demo_pattern = QComboBox()
        self.demo_pattern.addItems(self.DEMO_PATTERNS)
        self.demo_pattern.setEnabled(False)
        demo_grid.addWidget(QLabel("Mode"), 0, 0)
        demo_grid.addWidget(self.demo_pattern, 0, 1)
        
        self.contour_check = QCheckBox("Plot Contour")
        self.contour_check.setChecked(False)
        demo_grid.addWidget(self.contour_check, 1, 0, 1, 2)
        top.addWidget(demo_box, 1)
        root.addLayout(top)

        self.chart = QChart()
        self.chart.setTitle("Smith Chart (Z0 = 50 ohm)")
        self.chart.legend().hide()
        self.chart.setBackgroundVisible(True)
        self.chart.setBackgroundBrush(QColor("#FFF56B"))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.setPlotAreaBackgroundBrush(QColor("#FFFFFF"))

        self.axis_x = QValueAxis()
        self.axis_x.setRange(-1.1, 1.1)
        self.axis_x.setTitleText("Re(Γ)")
        self.axis_x.setLabelFormat("%.1f")
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)

        self.axis_y = QValueAxis()
        self.axis_y.setRange(-1.1, 1.1)
        self.axis_y.setTitleText("Im(Γ)")
        self.axis_y.setLabelFormat("%.1f")
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)

        self._add_smith_grid()

        self.history_series = QScatterSeries()
        self.history_series.setColor(QColor("#000000"))
        self.history_series.setMarkerSize(8.0)
        self.chart.addSeries(self.history_series)
        self.history_series.attachAxis(self.axis_x)
        self.history_series.attachAxis(self.axis_y)

        self.active_series = QScatterSeries()
        self.active_series.setColor(QColor("#FF2020"))
        self.active_series.setMarkerSize(12.0)
        self.chart.addSeries(self.active_series)
        self.active_series.attachAxis(self.axis_x)
        self.active_series.attachAxis(self.axis_y)

        self.active_lf_series = QScatterSeries()
        self.active_lf_series.setColor(QColor("#007BFF"))
        self.active_lf_series.setMarkerSize(12.0)
        self.chart.addSeries(self.active_lf_series)
        self.active_lf_series.attachAxis(self.axis_x)
        self.active_lf_series.attachAxis(self.axis_y)

        self.chart_view = SmithChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        root.addWidget(self.chart_view, 1)

    def _add_smith_grid(self):
        boundary = _circle_series(0.0, 0.0, 1.0, QColor("#4F4F4F"), 2)
        self._attach_grid(boundary)

        for r_val in (0.2, 0.5, 1.0, 2.0, 5.0):
            center = r_val / (1.0 + r_val)
            radius = 1.0 / (1.0 + r_val)
            series = _circle_series(center, 0.0, radius, QColor("#B0B0B0"), 1)
            self._attach_grid(series)

        for x_val in (0.2, 0.5, 1.0, 2.0, 5.0):
            pos_arc = _reactance_arc_series(x_val, QColor("#B0B0B0"), 1)
            neg_arc = _reactance_arc_series(-x_val, QColor("#B0B0B0"), 1)
            self._attach_grid(pos_arc)
            self._attach_grid(neg_arc)

    def _attach_grid(self, series: QLineSeries):
        self.chart.addSeries(series)
        series.attachAxis(self.axis_x)
        series.attachAxis(self.axis_y)

    def set_demo_mode(self, enabled: bool):
        self.demo_pattern.setEnabled(enabled)

    def reset_points(self):
        self._gamma_points.clear()
        self._lf_gamma_points.clear()
        self.history_series.clear()
        self.active_series.clear()
        self.active_lf_series.clear()
        self._clear_contour()
        self._demo_step = 0
        self._active_r = 0.0
        self._active_x = 0.0
        self.load_r_edit.setText("0.00")
        self.load_x_edit.setText("0.00")

    def update_impedance(self, load_r: float | None, load_x: float | None):
        if load_r is None or load_x is None:
            return
        gamma = impedance_to_gamma(load_r, load_x)
        self._active_r = load_r
        self._active_x = load_x
        self._append_gamma(gamma)
        self.active_lf_series.clear()

    def update_dual_impedance(
        self,
        hf_r: float | None,
        hf_x: float | None,
        lf_r: float | None,
        lf_x: float | None,
    ):
        if hf_r is not None and hf_x is not None:
            hf_gamma = impedance_to_gamma(hf_r, hf_x)
            self._active_r = hf_r
            self._active_x = hf_x
            self._append_gamma(hf_gamma)
        if lf_r is None or lf_x is None:
            self.active_lf_series.clear()
            return
        lf_gamma = impedance_to_gamma(lf_r, lf_x)
        self._lf_gamma_points.append(lf_gamma)
        self.active_lf_series.clear()
        self.active_lf_series.append(lf_gamma.real, lf_gamma.imag)

    def append_demo_point(self):
        mode = self.demo_pattern.currentText()
        point = self._demo_point(mode, self._demo_step)
        self._demo_step += 1
        self._active_r = point[0]
        self._active_x = point[1]
        self._append_gamma(point[2])

    def _append_gamma(self, gamma: complex):
        self._gamma_points.append(gamma)
        self.history_series.clear()
        self.active_series.clear()
        points = list(self._gamma_points)
        for point in points[:-1]:
            self.history_series.append(point.real, point.imag)
        active = points[-1]
        self.active_series.append(active.real, active.imag)
        self.load_r_edit.setText(f"{self._active_r:.2f}")
        self.load_x_edit.setText(f"{self._active_x:.2f}")
    
    def plot_z_parameter_contour(
        self,
        z_params_list: list[ZParameters],
        clear: bool = True,
        color: QColor | None = None,
    ):
        """Plot one contour line or a set of lines without clearing previous ones unless requested."""
        if clear:
            self._clear_contour()

        if not z_params_list:
            return

        contour_series = QLineSeries()
        pen = contour_series.pen()
        pen.setColor(color or QColor("#FF8800"))
        pen.setWidth(2)
        contour_series.setPen(pen)

        for z_params in z_params_list:
            try:
                load_r, load_x = calculate_load_impedance_from_z_params(z_params)
                gamma = impedance_to_gamma(load_r, load_x)
                if abs(gamma) <= 1.001:
                    contour_series.append(gamma.real, gamma.imag)
            except Exception:
                continue

        if contour_series.count() > 0:
            self.chart.addSeries(contour_series)
            contour_series.attachAxis(self.axis_x)
            contour_series.attachAxis(self.axis_y)
            self._contour_series.append(contour_series)

    def _clear_contour(self):
        """Clear all contour series from the chart."""
        for series in self._contour_series:
            self.chart.removeSeries(series)
        self._contour_series = []

    def set_contour_cache(self, contour_data: dict[str, list[ZParameters]]):
        """Store contour data for later live plotting while RUN is active."""
        self._contour_cache = contour_data

    def show_contour(self, enabled: bool):
        """Show or hide the cached contour overlay without re-querying the device."""
        self._clear_contour()
        if not enabled:
            return
        preferred_keys = list(self._contour_cache.keys())
        if {"Line 1", "Line 2", "Line 3", "Line 4"}.issubset(self._contour_cache.keys()):
            preferred_keys = ["Line 1", "Line 2", "Line 3", "Line 4"]
        for line_name in preferred_keys:
            z_params_list = self._contour_cache.get(line_name, [])
            if not z_params_list:
                continue
            color = None
            lowered = line_name.lower()
            if lowered.startswith("hf "):
                color = QColor("#FF2020")
            elif lowered.startswith("lf "):
                color = QColor("#007BFF")
            self.plot_z_parameter_contour(z_params_list, clear=False, color=color)

    @staticmethod
    def _demo_point(mode: str, step: int) -> tuple[float, float, complex]:
        if mode == "VSWR=5 Circle":
            radius = 4.0 / 6.0
            angle = math.radians((step * 10) % 360)
            gamma = complex(radius * math.cos(angle), radius * math.sin(angle))
            load_r, load_x = gamma_to_impedance(gamma)
            return load_r, load_x, gamma
        if mode == "Spiral":
            angle = math.radians(step * 10)
            magnitude = min(80.0, 1.0 * (1.2 ** (step % 28)))
            load_r = max(1.0, 50.0 + (magnitude * math.cos(angle)))
            load_x = max(-500.0, min(500.0, magnitude * math.sin(angle)))
            gamma = impedance_to_gamma(load_r, load_x)
            return load_r, load_x, gamma
        if mode == "Linear":
            idx = step % 21
            t = -1.0 + idx * 0.1
            gamma = complex(t, t)
            load_r, load_x = gamma_to_impedance(gamma)
            return load_r, load_x, gamma
        load_r = float(random.randint(1, 10))
        load_x = random.uniform(-50.0, 50.0)
        gamma = impedance_to_gamma(load_r, load_x)
        return load_r, load_x, gamma


def _circle_series(center_x: float, center_y: float, radius: float, color: QColor, width: int) -> QLineSeries:
    series = QLineSeries()
    pen = series.pen()
    pen.setColor(color)
    pen.setWidth(width)
    series.setPen(pen)
    for deg in range(0, 361, 2):
        rad = math.radians(deg)
        x = center_x + (radius * math.cos(rad))
        y = center_y + (radius * math.sin(rad))
        series.append(x, y)
    return series


def _reactance_arc_series(reactance: float, color: QColor, width: int) -> QLineSeries:
    series = QLineSeries()
    pen = series.pen()
    pen.setColor(color)
    pen.setWidth(width)
    series.setPen(pen)
    for r_val in [x * 0.1 for x in range(0, 801)]:
        gamma = impedance_to_gamma(r_val * Z0_OHMS, reactance * Z0_OHMS)
        if abs(gamma) <= 1.001:
            series.append(gamma.real, gamma.imag)
    return series
