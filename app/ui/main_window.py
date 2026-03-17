import time
import numpy as np

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QScrollArea
)

from collections import deque
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtGui import QPainter

from backend.acquisition import AcquisitionWorker
from backend.optical_switch import Gezhi12SwitchController
from .distance_axis import DistanceAxis
from ..transformers.waterfall_transform import WaterfallTransform
from ..viz.waterfall_renderer import WaterfallRenderer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ---- Transform/Renderer ----
        self.transform = WaterfallTransform()
        self.transform.mode = "Energy (MSE dB)"  # default & only mode used
        self.renderer = WaterfallRenderer(wf_height=600)

        self.setWindowTitle("JMV-DAS Infrastructure Secure")
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout()
        central.setLayout(main_layout)

        # ---- Left controls (in scroll) ----
        control_layout = QVBoxLayout()

        # Acquisition params
        self.scan_rate = QComboBox()
        self.scan_rate.addItems(["1k", "2k", "4k", "10k"])
        self.scan_rate.setCurrentText("10k")

        self.mode = QComboBox()
        self.mode.addItems([
            "Coherent Suppression",
            "Polarization Suppression",
            "Coherent + Polarization"
        ])

        self.pulse_width = QSpinBox()
        self.pulse_width.setRange(1, 2000)
        self.pulse_width.setValue(100)

        self.scale_down = QSpinBox()
        self.scale_down.setRange(1, 10)
        self.scale_down.setValue(10)

        # Optical switch controls
        self.switch_port = QComboBox()
        self.switch_port.setEditable(True)
        self.btn_switch_refresh = QPushButton("Refresh Ports")
        self.btn_switch_connect = QPushButton("Connect Switch")
        self.btn_switch_disconnect = QPushButton("Disconnect Switch")
        self.switch_ch1 = QComboBox()
        self.switch_ch1.addItems(["OFF", "ON"])
        self.switch_ch2 = QComboBox()
        self.switch_ch2.addItems(["OFF", "ON"])
        self.btn_switch_apply = QPushButton("Apply Switch State")
        self.switch_status = QLabel("Switch: Disconnected")
        self.switch_status.setWordWrap(True)

        # Stream selection
        self.wf_channel = QComboBox()
        self.wf_channel.addItems(["1", "2"])
        self.wf_kind = QComboBox()
        self.wf_kind.addItems(["phase", "amp"])

        # ---- Time-series selection ----
        self.ts_col = QSpinBox()
        self.ts_col.setRange(0, 0)     # 先占位，等拿到 point_count 再更新范围
        self.ts_col.setValue(0)

        # ---- Energy(MSE dB) params ----
        self.energy_win = QSpinBox()
        self.energy_win.setRange(1, 4096)
        self.energy_win.setValue(32)

        self.db_vmin = QDoubleSpinBox()
        self.db_vmin.setRange(-2000.0, 2000.0)
        self.db_vmin.setDecimals(2)
        self.db_vmin.setSingleStep(1.0)
        self.db_vmin.setValue(self.transform.vmin)

        self.db_vmax = QDoubleSpinBox()
        self.db_vmax.setRange(-2000.0, 2000.0)
        self.db_vmax.setDecimals(2)
        self.db_vmax.setSingleStep(1.0)
        self.db_vmax.setValue(self.transform.vmax)

        self.gamma = QDoubleSpinBox()
        self.gamma.setRange(0.1, 5.0)
        self.gamma.setDecimals(2)
        self.gamma.setSingleStep(0.05)
        self.gamma.setValue(1.0)

        self.eps = QDoubleSpinBox()
        self.eps.setRange(1e-12, 1.0)
        self.eps.setDecimals(12)
        self.eps.setSingleStep(1e-6)
        self.eps.setValue(1e-6)

        self.invert = QCheckBox("Invert (background bright)")
        self.invert.setChecked(False)

        # Buttons
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")

        self.status = QLabel("Status: Idle")
        self.status.setWordWrap(True)

        # Layout (controls)
        control_layout.addWidget(QLabel("Scan Rate"))
        control_layout.addWidget(self.scan_rate)
        control_layout.addWidget(QLabel("Mode"))
        control_layout.addWidget(self.mode)
        control_layout.addWidget(QLabel("Pulse Width"))
        control_layout.addWidget(self.pulse_width)
        control_layout.addWidget(QLabel("Scale Down"))
        control_layout.addWidget(self.scale_down)

        control_layout.addSpacing(12)
        control_layout.addWidget(QLabel("Optical Switch Port"))
        control_layout.addWidget(self.switch_port)
        switch_port_buttons = QHBoxLayout()
        switch_port_buttons.addWidget(self.btn_switch_refresh)
        switch_port_buttons.addWidget(self.btn_switch_connect)
        control_layout.addLayout(switch_port_buttons)
        control_layout.addWidget(self.btn_switch_disconnect)
        control_layout.addWidget(QLabel("Optical Switch CH1"))
        control_layout.addWidget(self.switch_ch1)
        control_layout.addWidget(QLabel("Optical Switch CH2"))
        control_layout.addWidget(self.switch_ch2)
        control_layout.addWidget(self.btn_switch_apply)
        control_layout.addWidget(self.switch_status)

        control_layout.addSpacing(12)
        control_layout.addWidget(QLabel("Waterfall Channel"))
        control_layout.addWidget(self.wf_channel)
        control_layout.addWidget(QLabel("Waterfall Kind"))
        control_layout.addWidget(self.wf_kind)
        control_layout.addWidget(QLabel("Time Series Column (pos idx)"))
        control_layout.addWidget(self.ts_col)

        control_layout.addSpacing(12)
        control_layout.addWidget(QLabel("Transform: Energy (MSE dB)"))
        control_layout.addWidget(QLabel("Energy Window (lines)"))
        control_layout.addWidget(self.energy_win)
        control_layout.addWidget(QLabel("dB vmin"))
        control_layout.addWidget(self.db_vmin)
        control_layout.addWidget(QLabel("dB vmax"))
        control_layout.addWidget(self.db_vmax)
        control_layout.addWidget(QLabel("Gamma"))
        control_layout.addWidget(self.gamma)
        control_layout.addWidget(self.invert)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.status)
      
        # ---- Right panel: time-series (top) + waterfall (bottom) ----
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_widget.setLayout(right_layout)

        # Time-series chart
        self._ts_series = QLineSeries()
        self._ts_chart = QChart()
        self._ts_chart.legend().hide()
        self._ts_chart.addSeries(self._ts_series)
        self._ts_chart.setTitle("Time Series @ fixed column")

        self._ts_axis_x = QValueAxis()
        self._ts_axis_y = QValueAxis()
        self._ts_axis_x.setTitleText("t (s)")
        self._ts_axis_y.setTitleText("value")
        self._ts_chart.addAxis(self._ts_axis_x, Qt.AlignBottom)
        self._ts_chart.addAxis(self._ts_axis_y, Qt.AlignLeft)
        self._ts_series.attachAxis(self._ts_axis_x)
        self._ts_series.attachAxis(self._ts_axis_y)

        self.ts_view = QChartView(self._ts_chart)
        self.ts_view.setRenderHint(QPainter.Antialiasing, True)
        self.ts_view.setMinimumHeight(320)
        self.ts_view.setMaximumHeight(320)   # 你想更矮就改这里

        # Waterfall display (original)
        self.display = QLabel("Waterfall Display")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setStyleSheet("background-color: black; color: white;")
        self.display.setMinimumSize(800, 320)   # 让它比原来矮一些（你可再调
        self.display.setCursor(Qt.OpenHandCursor)

        # enable click-to-select-column on waterfall
        self.display.setMouseTracking(True)
        self.display.installEventFilter(self)
        self.distance_axis = DistanceAxis()

        # store latest point_count for mapping click x -> column
        self._last_point_count_for_click = 0

        right_layout.addWidget(self.ts_view, 0)
        right_layout.addWidget(self.display, 1)
        right_layout.addWidget(self.distance_axis, 0)
        self.hover_info = QLabel("Hover waterfall to inspect point")
        self.hover_info.setWordWrap(True)
        right_layout.addWidget(self.hover_info, 0)

        # ---- Put controls into a scroll area ----
        control_widget = QWidget()
        control_widget.setLayout(control_layout)

        scroll = QScrollArea()
        scroll.setWidget(control_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(280)

        main_layout.addWidget(scroll, 0)
        main_layout.addWidget(right_widget, 1)

        # ---- Worker ----
        self.worker = AcquisitionWorker()
        self.switch_controller = Gezhi12SwitchController()
        self.worker.data_ready.connect(self.on_data_ready)

        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_switch_refresh.clicked.connect(self._refresh_switch_ports)
        self.btn_switch_connect.clicked.connect(self.on_switch_connect_clicked)
        self.btn_switch_disconnect.clicked.connect(self.on_switch_disconnect_clicked)
        self.btn_switch_apply.clicked.connect(self.on_switch_apply_clicked)

        # ---- Data cache ----
        self._latest_by_stream = {}  # (ch, kind) -> payload

        # ---- Time-series cache ----
        self._ts_y = deque(maxlen=4000)   # 你想更长就改这里
        self._ts_t = deque(maxlen=4000)
        self._ts_last_t = 0.0
        self._ts_dt = 0.001               # default, will be updated from scan rate
        self._ts_last_point_count = None

        # ---- UI refresh throttling ----
        self._last_update_ts = 0.0
        self._min_ui_interval = 1.0 / 30.0  # 30 FPS

        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / 30))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # When selection/params change, allow next tick immediately
        self.wf_channel.currentIndexChanged.connect(self._on_stream_selection_changed)
        self.wf_kind.currentIndexChanged.connect(self._on_stream_selection_changed)
        self.energy_win.valueChanged.connect(self._poke_refresh)
        self.db_vmin.valueChanged.connect(self._poke_refresh)
        self.db_vmax.valueChanged.connect(self._poke_refresh)
        self.gamma.valueChanged.connect(self._poke_refresh)
        self.eps.valueChanged.connect(self._poke_refresh)
        self.invert.stateChanged.connect(self._poke_refresh)
        self.ts_col.valueChanged.connect(self._poke_refresh)
        self.ts_col.valueChanged.connect(self._on_ts_col_changed)
        self.scale_down.valueChanged.connect(self._update_distance_axis_from_ui)

        self._wf_src_w = 0   # renderer.wf_width == point_count
        self._wf_src_h = 0   # renderer.wf_height
        self._wf_scale_down = int(self.scale_down.value())
        self._wf_view_start_col = 0
        self._wf_view_col_count = 0
        self._wf_zoom_factor = 1.25
        self._wf_min_view_cols = 16
        self._wf_drag_active = False
        self._wf_drag_moved = False
        self._wf_drag_start_x = 0.0
        self._wf_drag_origin_start_col = 0

        self._update_ts_title()
        self._update_distance_axis_from_ui()
        self._refresh_switch_ports()

    def _poke_refresh(self, *args):
        self._last_update_ts = 0.0

    def _selected_stream(self) -> tuple[int, str]:
        try:
            sel_ch = int(self.wf_channel.currentText())
        except Exception:
            sel_ch = 1
        sel_kind = self.wf_kind.currentText() or "phase"
        return sel_ch, sel_kind

    def _clear_selected_stream_view(self):
        self._clear_timeseries_cache()
        self._ts_last_t = 0.0
        self._ts_series.clear()
        self.renderer.clear()
        self.display.clear()
        self.display.setText("Waiting for selected stream...")
        self.display.setToolTip("")
        self.hover_info.setText("Hover waterfall to inspect point")
        self._last_update_ts = 0.0
        self._update_ts_title()

    def _on_stream_selection_changed(self, *args):
        self._clear_selected_stream_view()
        sel_ch, sel_kind = self._selected_stream()
        self.status.setText(f"Status: Waiting for ch{sel_ch}/{sel_kind} data")

    def _update_distance_axis_from_ui(self, *args):
        self._clamp_viewport()
        self.distance_axis.set_axis_state(
            point_count=int(self._wf_src_w or 0),
            scale_down=int(self._wf_scale_down or self.scale_down.value()),
            selected_col=int(self.ts_col.value()),
            view_start_col=int(self._wf_view_start_col),
            view_point_count=int(self._effective_view_col_count()),
        )

    def _on_ts_col_changed(self, *args):
        self._ensure_selected_col_visible()
        self._update_ts_title()
        self._update_distance_axis_from_ui()

    def _effective_view_col_count(self, point_count: int | None = None) -> int:
        total_cols = int(self._wf_src_w if point_count is None else point_count)
        if total_cols <= 0:
            return 0

        view_col_count = int(self._wf_view_col_count or total_cols)
        return max(1, min(view_col_count, total_cols))

    def _clamp_viewport(self, point_count: int | None = None):
        total_cols = int(self._wf_src_w if point_count is None else point_count)
        if total_cols <= 0:
            self._wf_view_start_col = 0
            self._wf_view_col_count = 0
            return

        view_col_count = self._effective_view_col_count(total_cols)
        max_start = max(0, total_cols - view_col_count)
        self._wf_view_start_col = max(0, min(int(self._wf_view_start_col), max_start))
        self._wf_view_col_count = view_col_count

    def _set_viewport(self, start_col: int, col_count: int, render: bool = True):
        total_cols = int(self._wf_src_w or 0)
        if total_cols <= 0:
            self._wf_view_start_col = 0
            self._wf_view_col_count = 0
            return

        old_state = (int(self._wf_view_start_col), int(self._effective_view_col_count(total_cols)))
        self._wf_view_start_col = int(start_col)
        self._wf_view_col_count = int(col_count)
        self._clamp_viewport(total_cols)
        new_state = (int(self._wf_view_start_col), int(self._effective_view_col_count(total_cols)))

        if render and new_state != old_state:
            self._render_waterfall_view()

    def _reset_viewport(self):
        total_cols = int(self._wf_src_w or 0)
        if total_cols <= 0:
            return
        self._set_viewport(0, total_cols)

    def _render_waterfall_view(self):
        if self.renderer.wf is None or int(self._wf_src_w or 0) <= 0:
            return

        self._clamp_viewport()
        self.renderer.render_to_label(
            self.display,
            start_col=int(self._wf_view_start_col),
            col_count=int(self._effective_view_col_count()),
        )
        self._update_distance_axis_from_ui()
        self._update_ts_title()

    def _ensure_selected_col_visible(self):
        total_cols = int(self._wf_src_w or 0)
        if total_cols <= 0:
            return

        self._clamp_viewport(total_cols)
        view_col_count = self._effective_view_col_count(total_cols)
        selected_col = min(max(0, int(self.ts_col.value())), total_cols - 1)

        if selected_col < self._wf_view_start_col:
            self._set_viewport(selected_col, view_col_count)
        elif selected_col >= self._wf_view_start_col + view_col_count:
            self._set_viewport(selected_col - view_col_count + 1, view_col_count)

    def _clear_timeseries_cache(self):
        self._ts_y.clear()
        self._ts_t.clear()

    def _zoom_waterfall(self, x_px: float, zoom_in: bool):
        total_cols = int(self._wf_src_w or 0)
        if total_cols <= 1:
            return

        current_count = self._effective_view_col_count(total_cols)
        min_view_cols = min(total_cols, self._wf_min_view_cols)
        if zoom_in:
            new_count = max(min_view_cols, int(round(current_count / self._wf_zoom_factor)))
            if new_count == current_count and current_count > min_view_cols:
                new_count = current_count - 1
        else:
            new_count = min(total_cols, int(round(current_count * self._wf_zoom_factor)))
            if new_count == current_count and current_count < total_cols:
                new_count = current_count + 1

        if new_count == current_count:
            return

        display_width = max(1, int(self.display.width()))
        anchor_ratio = min(max((float(x_px) + 0.5) / display_width, 0.0), 1.0)
        anchor_col = self._x_to_col_exact(x_px)
        new_start = int(round(anchor_col - anchor_ratio * new_count))
        self._set_viewport(new_start, new_count)

    def _pan_waterfall(self, delta_x: float):
        total_cols = int(self._wf_src_w or 0)
        if total_cols <= 0:
            return

        view_col_count = self._effective_view_col_count(total_cols)
        if view_col_count >= total_cols:
            return

        display_width = max(1, int(self.display.width()))
        shift_cols = int(round(float(delta_x) * view_col_count / display_width))
        new_start = int(self._wf_drag_origin_start_col) - shift_cols
        self._set_viewport(new_start, view_col_count)

    def _current_column_distance_text(self, point_count: int, scale_down: int) -> str:
        if point_count <= 0:
            return "col=0, dist=n/a"

        col = min(max(0, int(self.ts_col.value())), point_count - 1)
        distance_m = col * DistanceAxis.base_spacing_m() * max(1, int(scale_down))
        return f"col={col}, dist={self.distance_axis._format_distance(distance_m)}"

    def _current_column_distance_label(self, point_count: int, scale_down: int) -> str:
        if point_count <= 0:
            return "column 0"

        col = min(max(0, int(self.ts_col.value())), point_count - 1)
        distance_m = col * DistanceAxis.base_spacing_m() * max(1, int(scale_down))
        return f"column {col} ({self.distance_axis._format_distance(distance_m)})"

    def on_start_clicked(self):
        try:
            scan_rate_label = self.scan_rate.currentText()
            mode_label = self.mode.currentText()
            pulse_width = int(self.pulse_width.value())
            scale_down = int(self.scale_down.value())

            self.status.setText("Status: Starting...")
            self.worker.start(scan_rate_label, mode_label, pulse_width, scale_down)
            self.status.setText(
                f"Status: Running (cfg_scan={scan_rate_label}, cfg_mode={mode_label}, pw={pulse_width}, sd={scale_down})"
            )
        except Exception as e:
            self.status.setText(f"Status: Start failed: {e}")

    def on_stop_clicked(self):
        try:
            self.worker.stop()
            self.status.setText("Status: Stopped")
        except Exception as e:
            self.status.setText(f"Status: Stop failed: {e}")

    def _refresh_switch_ports(self):
        current_text = (self.switch_port.currentText() or "").strip()
        ports = self.switch_controller.available_ports()

        self.switch_port.blockSignals(True)
        self.switch_port.clear()
        self.switch_port.addItems(ports)
        self.switch_port.blockSignals(False)

        if current_text:
            self.switch_port.setCurrentText(current_text)
        elif ports:
            self.switch_port.setCurrentText(ports[0])
        else:
            self.switch_port.setCurrentText("/dev/ttyUSB0")

    def on_switch_connect_clicked(self):
        try:
            port_name = (self.switch_port.currentText() or "").strip()
            self.switch_controller.open(port_name)
            self.switch_status.setText(f"Switch: Connected @ {self.switch_controller.port_name}")
        except Exception as e:
            self.switch_status.setText(f"Switch: Connect failed: {e}")

    def on_switch_disconnect_clicked(self):
        try:
            self.switch_controller.close()
            self.switch_status.setText("Switch: Disconnected")
        except Exception as e:
            self.switch_status.setText(f"Switch: Disconnect failed: {e}")

    def on_switch_apply_clicked(self):
        try:
            ch1_on = self.switch_ch1.currentText() == "ON"
            ch2_on = self.switch_ch2.currentText() == "ON"
            self.switch_controller.set_channels(ch1_on, ch2_on)
            self.switch_status.setText(
                f"Switch: Applied CH1={'ON' if ch1_on else 'OFF'}, CH2={'ON' if ch2_on else 'OFF'}"
            )
        except Exception as e:
            self.switch_status.setText(f"Switch: Apply failed: {e}")

    def on_data_ready(self, payload: dict):
        try:
            ch = int(payload.get("channel", 1))
            kind = str(payload.get("kind", "phase"))
            self._latest_by_stream[(ch, kind)] = payload
        except Exception:
            pass

    def _pull_selected_payload(self):
        sel_ch, sel_kind = self._selected_stream()
        key = (sel_ch, sel_kind)
        payload = self._latest_by_stream.get(key)
        if payload is None:
            return None, sel_ch, sel_kind
        self._latest_by_stream.pop(key, None)
        return payload, sel_ch, sel_kind

    def _sync_transform_params(self):
        # Only Energy(MSE dB) is used
        self.transform.mode = "Energy (MSE dB)"
        self.transform.energy_win = int(self.energy_win.value())
        self.transform.vmin = float(self.db_vmin.value())
        self.transform.vmax = float(self.db_vmax.value())
        self.transform.gamma = float(self.gamma.value())
        self.transform.eps = float(self.eps.value())
        self.transform.invert = bool(self.invert.isChecked())

    def _x_to_col_exact(self, x_px: float) -> int:
        """
        Exact mapping for WaterfallRenderer.render_to_label:
        - pixmap scaled to label.size() with Qt.IgnoreAspectRatio
        => full label area corresponds to full wf image (no padding).
        - We map label pixel coordinate to source column with pixel-center mapping.
        """
        src_w = int(self._wf_src_w or 0)  # == point_count
        if src_w <= 1:
            return 0

        dst_w = int(self.display.width())
        if dst_w <= 1:
            return 0

        self._clamp_viewport(src_w)
        view_start_col = int(self._wf_view_start_col)
        view_col_count = int(self._effective_view_col_count(src_w))

        # Clamp click into [0, dst_w)
        x = float(x_px)
        if x < 0.0:
            x = 0.0
        if x > (dst_w - 1):
            x = float(dst_w - 1)

        # Pixel-center mapping:
        # dst pixel center at (x + 0.5) maps to the current visible viewport.
        # u = (x+0.5)/dst_w * visible_cols
        # src index = floor(u)
        u = (x + 0.5) * view_col_count / dst_w
        col = view_start_col + int(u)  # floor

        col = max(view_start_col, min(col, view_start_col + view_col_count - 1))
        return col

    def _y_to_row_exact(self, y_px: float) -> int:
        src_h = int(self._wf_src_h or 0)
        if src_h <= 1:
            return 0

        dst_h = int(self.display.height())
        if dst_h <= 1:
            return 0

        y = float(y_px)
        if y < 0.0:
            y = 0.0
        if y > (dst_h - 1):
            y = float(dst_h - 1)

        u = (y + 0.5) * src_h / dst_h
        row = int(u)
        return max(0, min(row, src_h - 1))

    @staticmethod
    def _format_time_of_day(epoch_s: float) -> str:
        if not np.isfinite(epoch_s):
            return "n/a"
        whole = int(epoch_s)
        ms = int(round((epoch_s - whole) * 1000.0))
        if ms >= 1000:
            whole += 1
            ms = 0
        return f"{time.strftime('%H:%M:%S', time.localtime(whole))}.{ms:03d}"

    def _format_hover_value(self, value: float, kind: str) -> str:
        if not np.isfinite(value):
            return f"{kind}=n/a"
        if kind == "phase":
            return f"phase={value:.2f} deg"
        return f"amp={value:.4f}"

    def _set_hover_info(self, text: str):
        self.hover_info.setText(text)
        self.display.setToolTip(text)

    def _update_hover_info(self, x_px: float, y_px: float):
        if self.renderer.wf is None or self.renderer.values is None or self.renderer.row_times is None:
            self._set_hover_info("Hover waterfall to inspect point")
            return

        total_cols = int(self._wf_src_w or 0)
        total_rows = int(self._wf_src_h or 0)
        if total_cols <= 0 or total_rows <= 0:
            self._set_hover_info("Hover waterfall to inspect point")
            return

        col = self._x_to_col_exact(x_px)
        row = self._y_to_row_exact(y_px)
        if row < 0 or row >= self.renderer.values.shape[0] or col < 0 or col >= self.renderer.values.shape[1]:
            self._set_hover_info("Hover waterfall to inspect point")
            return

        sel_ch, sel_kind = self._selected_stream()
        distance_m = col * DistanceAxis.base_spacing_m() * max(1, int(self._wf_scale_down))
        value = float(self.renderer.values[row, col])
        row_time = float(self.renderer.row_times[row])

        delta_text = ""
        latest_time = float(self.renderer.row_times[-1]) if self.renderer.row_times.size > 0 else np.nan
        if np.isfinite(row_time) and np.isfinite(latest_time):
            age_s = max(0.0, latest_time - row_time)
            delta_text = f", age={age_s:.3f}s"

        text = (
            f"Hover ch{sel_ch}/{sel_kind}: "
            f"dist={self.distance_axis._format_distance(distance_m)}, "
            f"time={self._format_time_of_day(row_time)}{delta_text}, "
            f"{self._format_hover_value(value, sel_kind)}, "
            f"row={row}, col={col}"
        )
        self._set_hover_info(text)


    def eventFilter(self, obj, event):
        if obj is self.display:
            try:
                if event.type() == QEvent.Resize:
                    self._render_waterfall_view()
                    return False

                if event.type() == QEvent.Wheel:
                    delta_y = event.angleDelta().y()
                    if delta_y != 0:
                        self._zoom_waterfall(event.position().x(), zoom_in=delta_y > 0)
                    return True

                if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                    self._wf_drag_active = False
                    self._wf_drag_moved = False
                    self.display.setCursor(Qt.OpenHandCursor)
                    self._reset_viewport()
                    return True

                if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    self._wf_drag_active = True
                    self._wf_drag_moved = False
                    self._wf_drag_start_x = float(event.position().x())
                    self._wf_drag_origin_start_col = int(self._wf_view_start_col)
                    self.display.setCursor(Qt.ClosedHandCursor)
                    return True

                if event.type() == QEvent.MouseMove and self._wf_drag_active:
                    delta_x = float(event.position().x()) - self._wf_drag_start_x
                    if abs(delta_x) >= 3.0:
                        self._wf_drag_moved = True
                    if self._wf_drag_moved:
                        self._pan_waterfall(delta_x)
                    return True

                if event.type() == QEvent.MouseMove:
                    self._update_hover_info(event.position().x(), event.position().y())
                    return False

                if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    was_drag_active = self._wf_drag_active
                    was_drag_moved = self._wf_drag_moved
                    self._wf_drag_active = False
                    self._wf_drag_moved = False
                    self.display.setCursor(Qt.OpenHandCursor)

                    if was_drag_active and not was_drag_moved:
                        col = self._x_to_col_exact(event.position().x())
                        self.ts_col.setValue(col)
                        self._clear_timeseries_cache()
                        self._update_distance_axis_from_ui()
                    return was_drag_active

                if event.type() == QEvent.Leave:
                    self._set_hover_info("Hover waterfall to inspect point")
                    return False
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _parse_scan_rate_hz(self, scan_rate_label: str) -> float:
        # "1k" -> 1000, "10k" -> 10000
        try:
            s = (scan_rate_label or "").strip().lower()
            if s.endswith("k"):
                return float(s[:-1]) * 1000.0
            return float(s)
        except Exception:
            return 1000.0

    def _update_timeseries_from_block(self, block: np.ndarray, cfg_scan: str, point_count: int):
        # block: [num_lines, point_count]
        # pick selected column
        col = int(self.ts_col.value())
        if col < 0:
            col = 0
        if col >= point_count:
            col = point_count - 1 if point_count > 0 else 0

        # update spin range if point_count changed
        if self._ts_last_point_count != point_count:
            self._ts_last_point_count = point_count
            self.ts_col.blockSignals(True)
            self.ts_col.setRange(0, max(0, point_count - 1))
            self.ts_col.blockSignals(False)
            col = min(col, max(0, point_count - 1))

        # dt from scan rate
        hz = self._parse_scan_rate_hz(cfg_scan)
        if hz <= 0:
            hz = 1000.0
        self._ts_dt = 1.0 / hz

        y = block[:, col].astype(np.float32, copy=False)

        # append to cache
        for v in y:
            self._ts_last_t += self._ts_dt
            self._ts_t.append(self._ts_last_t)
            self._ts_y.append(float(v))

        # render into QtCharts
        n = len(self._ts_y)
        if n < 2:
            return

        # build series points
        self._ts_series.clear()
        t0 = self._ts_t[0]
        t1 = self._ts_t[-1]
        ymin = min(self._ts_y)
        ymax = max(self._ts_y)
        if ymin == ymax:
            ymin -= 1e-6
            ymax += 1e-6

        # 下采样一下，避免点太多导致 UI 卡（你可调整 target）
        target = 800
        step = max(1, n // target)

        for i in range(0, n, step):
            self._ts_series.append(self._ts_t[i], self._ts_y[i])

        self._ts_axis_x.setRange(t0, t1)
        self._ts_axis_y.setRange(ymin, ymax)

    def _tick(self):
        payload, sel_ch, sel_kind = self._pull_selected_payload()
        if payload is None:
            return

        now = time.time()
        if now - self._last_update_ts < self._min_ui_interval:
            return
        self._last_update_ts = now

        try:
            cfg_scan = payload.get("cfg_scan_rate", "")
            cfg_mode = payload.get("cfg_mode", "")
            pw = payload.get("cfg_pulse_width", "")
            sd = int(payload.get("cfg_scale_down", self.scale_down.value()) or self.scale_down.value())

            point_count = int(payload["point_count"])
            num_lines = int(payload["cb_lines"])
            block = payload["block"]

            self._last_point_count_for_click = point_count

            if point_count <= 0 or num_lines <= 0:
                return

            block = np.asarray(block, dtype=np.float32)
            if block.ndim != 2 or block.shape[1] != point_count:
                block = block.reshape((-1, point_count))
                num_lines = block.shape[0]
                if num_lines <= 0:
                    return

            self._update_timeseries_from_block(block, cfg_scan, point_count)
            self._sync_transform_params()

            prev_point_count = int(self._wf_src_w or 0)
            was_full_view = prev_point_count <= 0 or self._effective_view_col_count(prev_point_count) >= prev_point_count
            self.renderer.ensure(point_count)
            if self.renderer.wf is None:
                return
            
            self._wf_src_w = int(self.renderer.wf_width or point_count or 0)
            self._wf_src_h = int(self.renderer.wf_height or 0)
            self._wf_scale_down = int(sd)
            if was_full_view:
                self._wf_view_start_col = 0
                self._wf_view_col_count = point_count
            self._clamp_viewport(point_count)

            gray_block = self.transform.apply(block)
            block_end_ts = float(payload.get("ts", time.time()))
            line_times = block_end_ts - self._ts_dt * np.arange(num_lines - 1, -1, -1, dtype=np.float64)
            self.renderer.push_block(gray_block, raw_block=block, line_times=line_times)
            self._render_waterfall_view()

            self.status.setText(
                f"Status: Running (show=ch{sel_ch}/{sel_kind}, tf=Energy(MSE dB), "
                f"win={self.transform.energy_win}, dB=({self.transform.vmin:.1f},{self.transform.vmax:.1f}), "
                f"gamma={self.transform.gamma:.2f}, "
                f"cfg_scan={cfg_scan}, mode={cfg_mode}, pw={pw}, sd={sd}, "
                f"lines={num_lines}, points={point_count}, "
                f"{self._current_column_distance_text(point_count, sd)})"
            )

        except Exception as e:
            self.status.setText(f"Status: Render error: {e}")

    def _update_ts_title(self):
        sel_ch, sel_kind = self._selected_stream()
        self._ts_chart.setTitle(
            f"Time Series ch{sel_ch}/{sel_kind} @ "
            f"{self._current_column_distance_label(self._wf_src_w, self._wf_scale_down)}"
        )

    def closeEvent(self, event):
        try:
            self.worker.stop()
        except Exception:
            pass
        try:
            self.switch_controller.close()
        except Exception:
            pass
        event.accept()
