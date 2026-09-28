from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis

from evc_gui.services.phase2 import EvcSample


class AxisClickableChartView(QChartView):
    y_axis_clicked = Signal(str)

    def mousePressEvent(self, event):
        plot = self.chart().plotArea()
        x = event.position().x()
        y = event.position().y()
        if plot.top() <= y <= plot.bottom():
            if plot.left() - 70 <= x <= plot.left() - 4:
                self.y_axis_clicked.emit("left")
            elif plot.right() + 4 <= x <= plot.right() + 90:
                self.y_axis_clicked.emit("right")
        super().mousePressEvent(event)


class AxisScaleDialog(QDialog):
    def __init__(self, parent: QWidget, axis_name: str, current_min: float, current_max: float):
        super().__init__(parent)
        self.setWindowTitle(f"Set {axis_name} Scale")
        self.setStyleSheet(
            """
            QDialog { background: #ffffff; }
            QLabel { color: #000000; }
            QDoubleSpinBox { color: #000000; background: #ffffff; border: 1px solid #909090; }
            """
        )
        self._min = QDoubleSpinBox()
        self._max = QDoubleSpinBox()
        self._step = QDoubleSpinBox()
        for spin in (self._min, self._max, self._step):
            spin.setDecimals(6)
            spin.setRange(-1_000_000_000, 1_000_000_000)
        self._min.setValue(current_min)
        self._max.setValue(current_max)
        default_step = (current_max - current_min) / 10.0 if current_max > current_min else 1.0
        self._step.setValue(max(default_step, 0.000001))
        self._step.setMinimum(0.000001)

        form = QFormLayout(self)
        hint = QLabel("Enter numeric values. Min Y must be less than Max Y. Step must be positive.")
        hint.setWordWrap(True)
        form.addRow(hint)
        form.addRow("Min Y value", self._min)
        form.addRow("Max Y value", self._max)
        form.addRow("Step size", self._step)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[float, float, float]:
        return self._min.value(), self._max.value(), self._step.value()


class PowerScopeWidget(QWidget):
    METRICS = [
        ("pfwd", "FWD", QColor("#2E86FF")),
        ("pref", "REV", QColor("#FF5252")),
        ("c1", "C1 Pos", QColor("#32CD32")),
        ("c2", "C2 Pos", QColor("#FF52FF")),
        ("vpp", "Vpp", QColor("#D8D86A")),
        ("dc_bias", "DcBias", QColor("#66D9EF")),
        ("pout", "Pout", QColor("#FFA726")),
        ("iout", "Iout", QColor("#AB47BC")),
    ]

    def __init__(self):
        super().__init__()
        self._series: dict[str, QLineSeries] = {}
        self._checks: dict[str, QCheckBox] = {}
        self._value_edits: dict[str, QLineEdit] = {}
        self._axis_scale_overrides: dict[str, tuple[float, float, float]] = {}
        self._quantum_lf_available = False
        self._axes_usage = {
            "power": {"pfwd", "pref", "pout"},
            "cap": {"c1", "c2"},
            "vpp": {"vpp"},
            "dc_bias": {"dc_bias"},
            "current": {"iout"},
        }
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        value_box = QGroupBox("Current Value")
        value_grid = QGridLayout(value_box)
        for idx, (key, label, _) in enumerate(self.METRICS):
            edit = QLineEdit("0")
            edit.setReadOnly(True)
            self._value_edits[key] = edit
            value_grid.addWidget(QLabel(label), idx // 4 * 2, (idx % 4) * 2)
            value_grid.addWidget(edit, idx // 4 * 2 + 1, (idx % 4) * 2)
        top.addWidget(value_box, 1)

        trace_box = QGroupBox("Chart Select")
        trace_grid = QGridLayout(trace_box)
        for idx, (key, label, color) in enumerate(self.METRICS):
            check = QCheckBox(label)
            check.setChecked(key in {"pfwd", "pref", "c1", "c2", "vpp", "dc_bias"})
            check.stateChanged.connect(self._apply_axis_visibility)
            check.setStyleSheet(f"QCheckBox {{ color: {color.name()}; font-weight: 700; }}")
            self._checks[key] = check
            trace_grid.addWidget(check, idx, 0)
        trace_grid.addWidget(QLabel("Time Window"), len(self.METRICS), 0)
        self.time_window = QComboBox()
        self.time_window.addItems(["10 sec", "60 sec"])
        trace_grid.addWidget(self.time_window, len(self.METRICS) + 1, 0)
        trace_grid.addWidget(QLabel("Band"), len(self.METRICS) + 2, 0)
        self.band_selector = QComboBox()
        self.band_selector.addItems(["HF", "LF"])
        self.band_selector.setEnabled(False)
        trace_grid.addWidget(self.band_selector, len(self.METRICS) + 3, 0)
        top.addWidget(trace_box, 0)
        root.addLayout(top)

        self.chart = QChart()
        self.chart.legend().setVisible(True)
        self.chart.setBackgroundVisible(True)
        self.chart.setBackgroundBrush(QColor("#FFF56B"))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.setPlotAreaBackgroundBrush(QColor("#FFFFFF"))
        self.chart.setTitle("Scope")

        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("hh:mm:ss")
        self.axis_x.setTitleText("Time")
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)

        self.axis_power = QValueAxis()
        self.axis_power.setTitleText("Power Level")
        self.chart.addAxis(self.axis_power, Qt.AlignLeft)

        self.axis_cap = QValueAxis()
        self.axis_cap.setTitleText("Cap position")
        self.axis_cap.setRange(0, 100)
        self.chart.addAxis(self.axis_cap, Qt.AlignRight)

        self.axis_vpp = QValueAxis()
        self.axis_vpp.setTitleText("Vpp")
        self.chart.addAxis(self.axis_vpp, Qt.AlignRight)

        self.axis_dc = QValueAxis()
        self.axis_dc.setTitleText("DcBias")
        self.chart.addAxis(self.axis_dc, Qt.AlignRight)

        self.axis_iout = QValueAxis()
        self.axis_iout.setTitleText("Iout")
        self.chart.addAxis(self.axis_iout, Qt.AlignRight)

        for key, label, color in self.METRICS:
            series = QLineSeries()
            series.setName(label)
            series.setColor(color)
            self.chart.addSeries(series)
            series.attachAxis(self.axis_x)
            series.attachAxis(self._axis_for_key(key))
            self._series[key] = series

        chart_view = AxisClickableChartView(self.chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.y_axis_clicked.connect(self._on_y_axis_clicked)
        root.addWidget(chart_view, 1)
        self._apply_axis_visibility()

    def selected_seconds(self) -> int:
        return 60 if "60" in self.time_window.currentText() else 10

    def update_latest(self, sample: EvcSample | None):
        if not sample:
            return
        self._update_band_availability(sample)
        mapping = self._sample_mapping(sample)
        for key, value in mapping.items():
            suffix = "%" if key in {"c1", "c2"} else ""
            self._value_edits[key].setText(f"{value:.2f}{suffix}")

    def update_chart(self, samples: list[EvcSample]):
        if not samples:
            return
        key_values: dict[str, list[float]] = {key: [] for key, _, _ in self.METRICS}
        for series in self._series.values():
            series.clear()
        for sample in samples:
            stamp = _to_msec(sample.timestamp)
            self._update_band_availability(sample)
            values = self._sample_mapping(sample)
            for key, value in values.items():
                key_values[key].append(value)
                if self._checks[key].isChecked():
                    self._series[key].append(stamp, value)
        for key in self._series:
            self._series[key].setVisible(self._checks[key].isChecked())
        end = _to_msec(samples[-1].timestamp)
        start = end - (self.selected_seconds() * 1000)
        self.axis_x.setRange(QDateTime.fromMSecsSinceEpoch(start), QDateTime.fromMSecsSinceEpoch(end))
        self._apply_or_auto_scale(
            self.axis_power,
            "power",
            _collect_group_values(key_values, self._axes_usage["power"]),
        )
        self._apply_or_auto_scale(
            self.axis_cap,
            "cap",
            _collect_group_values(key_values, self._axes_usage["cap"]),
            default_range=(0.0, 100.0),
        )
        self._apply_or_auto_scale(
            self.axis_vpp,
            "vpp",
            _collect_group_values(key_values, self._axes_usage["vpp"]),
        )
        self._apply_or_auto_scale(
            self.axis_dc,
            "dc_bias",
            _collect_group_values(key_values, self._axes_usage["dc_bias"]),
        )
        self._apply_or_auto_scale(
            self.axis_iout,
            "current",
            _collect_group_values(key_values, self._axes_usage["current"]),
        )
        self._apply_axis_visibility()

    def _apply_axis_visibility(self):
        self.axis_power.setVisible(self._group_selected(self._axes_usage["power"]))
        self.axis_cap.setVisible(self._group_selected(self._axes_usage["cap"]))
        self.axis_vpp.setVisible(self._group_selected(self._axes_usage["vpp"]))
        self.axis_dc.setVisible(self._group_selected(self._axes_usage["dc_bias"]))
        self.axis_iout.setVisible(self._group_selected(self._axes_usage["current"]))
        for key in self._series:
            self._series[key].setVisible(self._checks[key].isChecked())

    def _group_selected(self, keys: set[str]) -> bool:
        return any(self._checks[k].isChecked() for k in keys)

    def _axis_for_key(self, key: str) -> QValueAxis:
        if key in self._axes_usage["cap"]:
            return self.axis_cap
        if key in self._axes_usage["vpp"]:
            return self.axis_vpp
        if key in self._axes_usage["dc_bias"]:
            return self.axis_dc
        if key in self._axes_usage["current"]:
            return self.axis_iout
        return self.axis_power

    def _is_lf_selected(self) -> bool:
        return self.band_selector.isEnabled() and self.band_selector.currentText() == "LF"

    def _update_band_availability(self, sample: EvcSample):
        has_lf = (
            sample.lf_pfwd is not None
            or sample.lf_pref is not None
            or sample.lf_c1 is not None
            or sample.lf_c2 is not None
            or sample.lf_vpp is not None
            or sample.lf_dc_bias is not None
            or sample.lf_pout is not None
            or sample.lf_iout is not None
        )
        if has_lf and not self._quantum_lf_available:
            self._quantum_lf_available = True
            self.band_selector.setEnabled(True)

    def _sample_mapping(self, sample: EvcSample) -> dict[str, float]:
        if self._is_lf_selected():
            return {
                "pfwd": sample.lf_pfwd if sample.lf_pfwd is not None else sample.pfwd,
                "pref": sample.lf_pref if sample.lf_pref is not None else sample.pref,
                "c1": sample.lf_c1 if sample.lf_c1 is not None else sample.c1,
                "c2": sample.lf_c2 if sample.lf_c2 is not None else sample.c2,
                "vpp": sample.lf_vpp if sample.lf_vpp is not None else sample.vpp,
                "dc_bias": sample.lf_dc_bias if sample.lf_dc_bias is not None else sample.dc_bias,
                "pout": sample.lf_pout if sample.lf_pout is not None else sample.pout,
                "iout": sample.lf_iout if sample.lf_iout is not None else sample.iout,
            }
        return {
            "pfwd": sample.pfwd,
            "pref": sample.pref,
            "c1": sample.c1,
            "c2": sample.c2,
            "vpp": sample.vpp,
            "dc_bias": sample.dc_bias,
            "pout": sample.pout,
            "iout": sample.iout,
        }

    def _axis_info(self, axis_key: str) -> tuple[QValueAxis, str]:
        if axis_key == "cap":
            return self.axis_cap, "Cap position"
        if axis_key == "vpp":
            return self.axis_vpp, "Vpp"
        if axis_key == "dc_bias":
            return self.axis_dc, "DcBias"
        if axis_key == "current":
            return self.axis_iout, "Iout"
        return self.axis_power, "Power Level"

    def _visible_axis_keys_for_side(self, side: str) -> list[str]:
        if side == "left":
            return ["power"] if self.axis_power.isVisible() else []
        right_keys = []
        for key in ("cap", "vpp", "dc_bias", "current"):
            axis, _ = self._axis_info(key)
            if axis.isVisible():
                right_keys.append(key)
        return right_keys

    def _on_y_axis_clicked(self, side: str):
        axis_keys = self._visible_axis_keys_for_side(side)
        if not axis_keys:
            return
        axis_key = axis_keys[0]
        if len(axis_keys) > 1:
            labels = [self._axis_info(k)[1] for k in axis_keys]
            selected, ok = QInputDialog.getItem(self, "Select Y Axis", "Axis", labels, 0, False)
            if not ok:
                return
            axis_key = axis_keys[labels.index(selected)]
        axis, axis_label = self._axis_info(axis_key)
        dialog = AxisScaleDialog(self, axis_label, axis.min(), axis.max())
        if dialog.exec() != QDialog.Accepted:
            return
        min_y, max_y, step = dialog.values()
        if min_y >= max_y:
            QMessageBox.warning(self, "Invalid Scale", "Min Y must be less than Max Y.")
            return
        self._axis_scale_overrides[axis_key] = (min_y, max_y, step)
        axis.setRange(min_y, max_y)
        axis.setTickInterval(step)

    def _apply_or_auto_scale(
        self,
        axis: QValueAxis,
        axis_key: str,
        values: list[float],
        default_range: tuple[float, float] | None = None,
    ):
        override = self._axis_scale_overrides.get(axis_key)
        if override:
            min_y, max_y, step = override
            axis.setRange(min_y, max_y)
            axis.setTickInterval(step)
            return
        axis.setTickInterval(0.0)
        if default_range is not None:
            axis.setRange(default_range[0], default_range[1])
            return
        self._set_auto_range(axis, values)

    @staticmethod
    def _set_auto_range(axis: QValueAxis, values: list[float]):
        if not values:
            axis.setRange(-1, 1)
            return
        low = min(values)
        high = max(values)
        if low == high:
            pad = max(1.0, abs(low) * 0.1)
            axis.setRange(low - pad, high + pad)
            return
        pad = (high - low) * 0.1
        axis.setRange(low - pad, high + pad)


def _collect_group_values(values: dict[str, list[float]], keys: set[str]) -> list[float]:
    output: list[float] = []
    for key in keys:
        output.extend(values[key])
    return output


def _to_msec(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)
