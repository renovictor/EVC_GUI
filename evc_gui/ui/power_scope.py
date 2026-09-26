from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt
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
from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis

from evc_gui.services.phase2 import EvcSample


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

        chart_view = QChartView(self.chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        root.addWidget(chart_view, 1)
        self._apply_axis_visibility()

    def selected_seconds(self) -> int:
        return 60 if "60" in self.time_window.currentText() else 10

    def update_latest(self, sample: EvcSample | None):
        if not sample:
            return
        mapping = {
            "pfwd": sample.pfwd,
            "pref": sample.pref,
            "c1": sample.c1,
            "c2": sample.c2,
            "vpp": sample.vpp,
            "dc_bias": sample.dc_bias,
            "pout": sample.pout,
            "iout": sample.iout,
        }
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
            values = {
                "pfwd": sample.pfwd,
                "pref": sample.pref,
                "c1": sample.c1,
                "c2": sample.c2,
                "vpp": sample.vpp,
                "dc_bias": sample.dc_bias,
                "pout": sample.pout,
                "iout": sample.iout,
            }
            for key, value in values.items():
                key_values[key].append(value)
                if self._checks[key].isChecked():
                    self._series[key].append(stamp, value)
        for key in self._series:
            self._series[key].setVisible(self._checks[key].isChecked())
        end = _to_msec(samples[-1].timestamp)
        start = end - (self.selected_seconds() * 1000)
        self.axis_x.setRange(QDateTime.fromMSecsSinceEpoch(start), QDateTime.fromMSecsSinceEpoch(end))
        self._set_auto_range(self.axis_power, _collect_group_values(key_values, self._axes_usage["power"]))
        self.axis_cap.setRange(0, 100)
        self._set_auto_range(self.axis_vpp, _collect_group_values(key_values, self._axes_usage["vpp"]))
        self._set_auto_range(self.axis_dc, _collect_group_values(key_values, self._axes_usage["dc_bias"]))
        self._set_auto_range(self.axis_iout, _collect_group_values(key_values, self._axes_usage["current"]))
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
