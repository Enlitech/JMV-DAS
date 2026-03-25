import threading
import time
import numpy as np

from PySide6.QtCore import Qt, QTimer, QEvent, QSettings, QUrl
from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QScrollArea,
    QDialog, QTextBrowser, QMessageBox,
    QLineEdit, QFileDialog
)

from collections import deque
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtGui import QPainter, QDesktopServices

from app.services import DocsService, FibreMonitorService, SwitchService, WaterfallRecordingService
from backend.acquisition import AcquisitionWorker
from backend.compat_http_api import CompatHttpApiServer
from backend.machine_id import get_machine_id
from .distance_axis import DistanceAxis
from ..transformers.waterfall_transform import WaterfallTransform
from ..viz.waterfall_renderer import WaterfallRenderer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._settings = QSettings("Enlitech", "JMV-DAS")
        self._pending_ts_col: int | None = None
        self.machine_id = get_machine_id()

        # ---- Transform/Renderer ----
        self.transform = WaterfallTransform()
        self.transform.mode = "Energy (MSE dB)"  # default & only mode used
        self.renderer = WaterfallRenderer(wf_height=600)

        self.setWindowTitle(f"JMV-DAS Infrastructure Secure [{self.machine_id}]")
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
        self.switch_ch1.addItems(["Main", "Standby"])
        self.switch_ch2 = QComboBox()
        self.switch_ch2.addItems(["Main", "Standby"])
        self.btn_switch_apply = QPushButton("Apply Fibre Selection")
        self.switch_status = QLabel("Switch: Disconnected")
        self.switch_status.setWordWrap(True)

        # Fibre break detection
        self.break_monitor_channel = QComboBox()
        self.break_monitor_channel.addItems(["1", "2"])
        self.break_alpha = QDoubleSpinBox()
        self.break_alpha.setRange(0.001, 1.0)
        self.break_alpha.setDecimals(3)
        self.break_alpha.setSingleStep(0.01)
        self.break_alpha.setValue(0.2)
        self.break_threshold = QDoubleSpinBox()
        self.break_threshold.setRange(-1_000_000.0, 1_000_000.0)
        self.break_threshold.setDecimals(3)
        self.break_threshold.setSingleStep(10.0)
        self.break_threshold.setValue(1000.0)
        self.break_min_length = QDoubleSpinBox()
        self.break_min_length.setRange(0.0, 500_000.0)
        self.break_min_length.setDecimals(2)
        self.break_min_length.setSingleStep(10.0)
        self.break_min_length.setValue(100.0)
        self.break_enable_alarm = QCheckBox("Enable Fibre Alarm")
        self.break_enable_alarm.setChecked(True)
        self.break_enable_autoswitch = QCheckBox("Auto Switch On Break")
        self.break_enable_autoswitch.setChecked(False)
        self.break_default_fibre = QComboBox()
        self.break_default_fibre.addItems(["Main", "Standby"])
        self.break_enable_peek = QCheckBox("Peek Other Fibre")
        self.break_enable_peek.setChecked(False)
        self.break_peek_interval = QSpinBox()
        self.break_peek_interval.setRange(1, 100000)
        self.break_peek_interval.setValue(20)
        self.break_peek_delay_ms = QSpinBox()
        self.break_peek_delay_ms.setRange(0, 5000)
        self.break_peek_delay_ms.setValue(200)
        self.break_status = QLabel("Fibre Break: Waiting for amp data")
        self.break_status.setWordWrap(True)

        # Stream selection
        self.wf_channel = QComboBox()
        self.wf_channel.addItems(["1", "2"])
        self.wf_kind = QComboBox()
        self.wf_kind.addItems(["phase", "amp"])
        self.wf_history_seconds = QDoubleSpinBox()
        self.wf_history_seconds.setRange(0.1, 3600.0)
        self.wf_history_seconds.setDecimals(1)
        self.wf_history_seconds.setSingleStep(1.0)
        self.wf_history_seconds.setValue(10.0)
        self.wf_range_enabled = QCheckBox("Enable Range Filter")
        self.wf_range_start_m = QDoubleSpinBox()
        self.wf_range_start_m.setRange(0.0, 1_000_000.0)
        self.wf_range_start_m.setDecimals(2)
        self.wf_range_start_m.setSingleStep(10.0)
        self.wf_range_start_m.setValue(0.0)
        self.wf_range_end_m = QDoubleSpinBox()
        self.wf_range_end_m.setRange(0.0, 1_000_000.0)
        self.wf_range_end_m.setDecimals(2)
        self.wf_range_end_m.setSingleStep(10.0)
        self.wf_range_end_m.setValue(500.0)
        self.btn_wf_range_use_view = QPushButton("Use Current View")
        self.btn_wf_range_reset = QPushButton("Reset Full Range")
        self.wf_range_status = QLabel("Range Filter: Full Range")
        self.wf_range_status.setWordWrap(True)

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
        self.btn_save_snapshot = QPushButton("Save Snapshot")
        self.btn_record_start = QPushButton("Start Recording")
        self.btn_record_stop = QPushButton("Stop Recording")
        self.btn_record_browse = QPushButton("Browse Folder")
        self.btn_record_open = QPushButton("Open Folder")
        self.btn_api_docs = QPushButton("API Docs")
        self.btn_user_guide = QPushButton("User Guide")
        self.record_mode = QComboBox()
        self.record_mode.addItem("Selected Stream", "selected")
        self.record_mode.addItem("All Streams", "all")
        self.record_scope = QComboBox()
        self.record_scope.addItem("Record Full Block", "full")
        self.record_scope.addItem("Record Filtered Range", "filtered")
        self.record_output_dir = QLineEdit()
        self.record_status = QLabel("Recording: Idle")
        self.record_status.setWordWrap(True)

        self.machine_id_label = QLabel(f"Machine ID: {self.machine_id}")
        self.machine_id_label.setWordWrap(True)
        self.clock_label = QLabel("Time: --")
        self.clock_label.setWordWrap(True)
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
        control_layout.addWidget(QLabel("Optical Switch CH1 Fibre"))
        control_layout.addWidget(self.switch_ch1)
        control_layout.addWidget(QLabel("Optical Switch CH2 Fibre"))
        control_layout.addWidget(self.switch_ch2)
        control_layout.addWidget(self.btn_switch_apply)
        control_layout.addWidget(self.switch_status)

        control_layout.addSpacing(12)
        control_layout.addWidget(QLabel("Fibre Break Monitor Channel"))
        control_layout.addWidget(self.break_monitor_channel)
        control_layout.addWidget(QLabel("Fibre Break EWMA Alpha"))
        control_layout.addWidget(self.break_alpha)
        control_layout.addWidget(QLabel("Fibre Break Amp Threshold"))
        control_layout.addWidget(self.break_threshold)
        control_layout.addWidget(QLabel("Fibre Break Min Length (m)"))
        control_layout.addWidget(self.break_min_length)
        control_layout.addWidget(QLabel("Default Fibre"))
        control_layout.addWidget(self.break_default_fibre)
        control_layout.addWidget(self.break_enable_alarm)
        control_layout.addWidget(self.break_enable_autoswitch)
        control_layout.addWidget(self.break_enable_peek)
        control_layout.addWidget(QLabel("Peek Every N Amp Blocks"))
        control_layout.addWidget(self.break_peek_interval)
        control_layout.addWidget(QLabel("Peek Settle Delay (ms)"))
        control_layout.addWidget(self.break_peek_delay_ms)
        control_layout.addWidget(self.break_status)

        control_layout.addSpacing(12)
        control_layout.addWidget(QLabel("Waterfall Channel"))
        control_layout.addWidget(self.wf_channel)
        control_layout.addWidget(QLabel("Waterfall Kind"))
        control_layout.addWidget(self.wf_kind)
        control_layout.addWidget(QLabel("Waterfall History (s)"))
        control_layout.addWidget(self.wf_history_seconds)
        control_layout.addWidget(self.wf_range_enabled)
        control_layout.addWidget(QLabel("Range Start Distance (m)"))
        control_layout.addWidget(self.wf_range_start_m)
        control_layout.addWidget(QLabel("Range End Distance (m)"))
        control_layout.addWidget(self.wf_range_end_m)
        control_layout.addWidget(self.btn_wf_range_use_view)
        control_layout.addWidget(self.btn_wf_range_reset)
        control_layout.addWidget(self.wf_range_status)
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

        control_layout.addSpacing(12)
        control_layout.addWidget(QLabel("Recording Mode"))
        control_layout.addWidget(self.record_mode)
        control_layout.addWidget(QLabel("Recording Scope"))
        control_layout.addWidget(self.record_scope)
        control_layout.addWidget(QLabel("Recording Output Folder"))
        control_layout.addWidget(self.record_output_dir)
        control_layout.addWidget(self.btn_record_browse)
        control_layout.addWidget(self.btn_record_open)
        control_layout.addWidget(self.btn_save_snapshot)
        control_layout.addWidget(self.btn_record_start)
        control_layout.addWidget(self.btn_record_stop)
        control_layout.addWidget(self.record_status)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_api_docs)
        control_layout.addWidget(self.btn_user_guide)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.machine_id_label)
        control_layout.addWidget(self.clock_label)
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
        self.fibre_monitor = FibreMonitorService()
        self.switch_service = SwitchService()
        self.docs_service = DocsService()
        self.recording_service = WaterfallRecordingService()
        self.compat_api = CompatHttpApiServer()
        self.worker.data_ready.connect(self.on_data_ready)

        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_save_snapshot.clicked.connect(self.on_save_snapshot_clicked)
        self.btn_record_start.clicked.connect(self.on_record_start_clicked)
        self.btn_record_stop.clicked.connect(self.on_record_stop_clicked)
        self.btn_record_browse.clicked.connect(self.on_record_browse_clicked)
        self.btn_record_open.clicked.connect(self.on_record_open_clicked)
        self.btn_api_docs.clicked.connect(self.on_api_docs_clicked)
        self.btn_user_guide.clicked.connect(self.on_user_guide_clicked)
        self.btn_wf_range_use_view.clicked.connect(self.on_wf_range_use_view_clicked)
        self.btn_wf_range_reset.clicked.connect(self.on_wf_range_reset_clicked)
        self.btn_switch_refresh.clicked.connect(self._refresh_switch_ports)
        self.btn_switch_connect.clicked.connect(self.on_switch_connect_clicked)
        self.btn_switch_disconnect.clicked.connect(self.on_switch_disconnect_clicked)
        self.btn_switch_apply.clicked.connect(self.on_switch_apply_clicked)
        self.break_monitor_channel.currentIndexChanged.connect(self._reset_fibre_break_detector)
        self.break_alpha.valueChanged.connect(self._reset_fibre_break_detector)
        self.break_threshold.valueChanged.connect(self._reset_fibre_break_detector)
        self.break_min_length.valueChanged.connect(self._reset_fibre_break_detector)
        self.break_default_fibre.currentIndexChanged.connect(self._reset_fibre_break_detector)
        self.break_enable_alarm.stateChanged.connect(self._update_fibre_break_status)
        self.break_enable_autoswitch.stateChanged.connect(self._update_fibre_break_status)
        self.break_enable_peek.stateChanged.connect(self._reset_fibre_break_detector)
        self.break_peek_interval.valueChanged.connect(self._reset_fibre_break_detector)
        self.break_peek_delay_ms.valueChanged.connect(self._reset_fibre_break_detector)

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
        self.wf_history_seconds.valueChanged.connect(self._on_wf_history_changed)
        self.wf_range_enabled.stateChanged.connect(self._on_wf_range_changed)
        self.wf_range_start_m.valueChanged.connect(self._on_wf_range_changed)
        self.wf_range_end_m.valueChanged.connect(self._on_wf_range_changed)
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
        self._wf_source_point_count = 0
        self._wf_data_start_col = 0
        self._wf_data_source_end_col = 0
        self._wf_history_target_s = float(self.wf_history_seconds.value())
        self._wf_history_effective_s = 0.0
        self._wf_view_start_col = 0
        self._wf_view_col_count = 0
        self._wf_zoom_factor = 1.25
        self._wf_min_view_cols = 16
        self._wf_drag_active = False
        self._wf_drag_moved = False
        self._wf_drag_start_x = 0.0
        self._wf_drag_origin_start_col = 0
        self._api_snapshot_lock = threading.Lock()
        self._api_snapshot = {
            "machine_id": self.machine_id,
            "channel_count": 2,
            "alerts": [],
            "alert_status_by_name": {},
            "fibre_health": [],
        }
        self._docs_dialogs: dict[str, tuple[QDialog, QTextBrowser]] = {}

        self._update_ts_title()
        self._update_distance_axis_from_ui()
        self._refresh_switch_ports()
        self._load_settings()
        self._sync_switch_state_from_ui()
        self._update_fibre_break_status()
        self._update_wf_range_status()
        self._update_api_snapshot()
        self._refresh_recording_status()
        self._update_clock_label()
        self.compat_api.set_snapshot(self._get_api_snapshot())
        if not self.compat_api.start():
            self.status.setText(f"Status: API listen failed on :{self.compat_api.port}: {self.compat_api.last_error}")

    @staticmethod
    def _settings_bool(value, default: bool = False) -> bool:
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _settings_int(value, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _settings_float(value, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _normalize_fibre_name(value, default: str = "main") -> str:
        return FibreMonitorService.normalize_fibre_name(str(value or ""), default=default)

    @staticmethod
    def _display_fibre_name(fibre_name: str) -> str:
        return "Standby" if FibreMonitorService.normalize_fibre_name(fibre_name) == "standby" else "Main"

    def _combo_fibre_name(self, combo: QComboBox, default: str = "main") -> str:
        return self._normalize_fibre_name(combo.currentText(), default=default)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str):
        text = (value or "").strip()
        if not text:
            return
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(text)

    def _save_settings(self):
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("acquisition/scan_rate", self.scan_rate.currentText())
        self._settings.setValue("acquisition/mode", self.mode.currentText())
        self._settings.setValue("acquisition/pulse_width", self.pulse_width.value())
        self._settings.setValue("acquisition/scale_down", self.scale_down.value())

        self._settings.setValue("switch/port", self.switch_port.currentText())
        self._settings.setValue("switch/ch1", self.switch_ch1.currentText())
        self._settings.setValue("switch/ch2", self.switch_ch2.currentText())

        self._settings.setValue("fibre_break/monitor_channel", self.break_monitor_channel.currentText())
        self._settings.setValue("fibre_break/alpha", self.break_alpha.value())
        self._settings.setValue("fibre_break/threshold", self.break_threshold.value())
        self._settings.setValue("fibre_break/min_length", self.break_min_length.value())
        self._settings.setValue("fibre_break/default_fibre", self.break_default_fibre.currentText())
        self._settings.setValue("fibre_break/enable_alarm", self.break_enable_alarm.isChecked())
        self._settings.setValue("fibre_break/enable_autoswitch", self.break_enable_autoswitch.isChecked())
        self._settings.setValue("fibre_break/enable_peek", self.break_enable_peek.isChecked())
        self._settings.setValue("fibre_break/peek_interval", self.break_peek_interval.value())
        self._settings.setValue("fibre_break/peek_delay_ms", self.break_peek_delay_ms.value())

        self._settings.setValue("waterfall/channel", self.wf_channel.currentText())
        self._settings.setValue("waterfall/kind", self.wf_kind.currentText())
        self._settings.setValue("waterfall/history_seconds", self.wf_history_seconds.value())
        self._settings.setValue("waterfall/range_enabled", self.wf_range_enabled.isChecked())
        self._settings.setValue("waterfall/range_start_m", self.wf_range_start_m.value())
        self._settings.setValue("waterfall/range_end_m", self.wf_range_end_m.value())
        self._settings.setValue("waterfall/ts_col", self.ts_col.value())

        self._settings.setValue("transform/energy_win", self.energy_win.value())
        self._settings.setValue("transform/db_vmin", self.db_vmin.value())
        self._settings.setValue("transform/db_vmax", self.db_vmax.value())
        self._settings.setValue("transform/gamma", self.gamma.value())
        self._settings.setValue("transform/eps", self.eps.value())
        self._settings.setValue("transform/invert", self.invert.isChecked())

        self._settings.setValue("recording/mode", self.record_mode.currentData())
        self._settings.setValue("recording/scope", self.record_scope.currentData())
        self._settings.setValue("recording/output_dir", self.record_output_dir.text())
        self._settings.sync()

    def _load_settings(self):
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass

        self._set_combo_text(
            self.scan_rate,
            str(self._settings.value("acquisition/scan_rate", self.scan_rate.currentText())),
        )
        self._set_combo_text(
            self.mode,
            str(self._settings.value("acquisition/mode", self.mode.currentText())),
        )
        self.pulse_width.setValue(
            self._settings_int(self._settings.value("acquisition/pulse_width"), self.pulse_width.value())
        )
        self.scale_down.setValue(
            self._settings_int(self._settings.value("acquisition/scale_down"), self.scale_down.value())
        )

        self._set_combo_text(
            self.switch_port,
            str(self._settings.value("switch/port", self.switch_port.currentText())),
        )
        self._set_combo_text(
            self.switch_ch1,
            self._display_fibre_name(self._settings.value("switch/ch1", self.switch_ch1.currentText())),
        )
        self._set_combo_text(
            self.switch_ch2,
            self._display_fibre_name(self._settings.value("switch/ch2", self.switch_ch2.currentText())),
        )

        self._set_combo_text(
            self.break_monitor_channel,
            str(self._settings.value("fibre_break/monitor_channel", self.break_monitor_channel.currentText())),
        )
        self.break_alpha.setValue(
            self._settings_float(self._settings.value("fibre_break/alpha"), self.break_alpha.value())
        )
        self.break_threshold.setValue(
            self._settings_float(self._settings.value("fibre_break/threshold"), self.break_threshold.value())
        )
        self.break_min_length.setValue(
            self._settings_float(self._settings.value("fibre_break/min_length"), self.break_min_length.value())
        )
        self._set_combo_text(
            self.break_default_fibre,
            self._display_fibre_name(
                self._settings.value("fibre_break/default_fibre", self.break_default_fibre.currentText())
            ),
        )
        self.break_enable_alarm.setChecked(
            self._settings_bool(self._settings.value("fibre_break/enable_alarm"), self.break_enable_alarm.isChecked())
        )
        self.break_enable_autoswitch.setChecked(
            self._settings_bool(
                self._settings.value("fibre_break/enable_autoswitch"),
                self.break_enable_autoswitch.isChecked(),
            )
        )
        self.break_enable_peek.setChecked(
            self._settings_bool(self._settings.value("fibre_break/enable_peek"), self.break_enable_peek.isChecked())
        )
        self.break_peek_interval.setValue(
            self._settings_int(self._settings.value("fibre_break/peek_interval"), self.break_peek_interval.value())
        )
        self.break_peek_delay_ms.setValue(
            self._settings_int(
                self._settings.value("fibre_break/peek_delay_ms"),
                self.break_peek_delay_ms.value(),
            )
        )

        self._set_combo_text(
            self.wf_channel,
            str(self._settings.value("waterfall/channel", self.wf_channel.currentText())),
        )
        self._set_combo_text(
            self.wf_kind,
            str(self._settings.value("waterfall/kind", self.wf_kind.currentText())),
        )
        self.wf_history_seconds.setValue(
            self._settings_float(
                self._settings.value("waterfall/history_seconds"),
                self.wf_history_seconds.value(),
            )
        )
        self.wf_range_enabled.setChecked(
            self._settings_bool(self._settings.value("waterfall/range_enabled"), self.wf_range_enabled.isChecked())
        )
        self.wf_range_start_m.setValue(
            self._settings_float(self._settings.value("waterfall/range_start_m"), self.wf_range_start_m.value())
        )
        self.wf_range_end_m.setValue(
            self._settings_float(self._settings.value("waterfall/range_end_m"), self.wf_range_end_m.value())
        )
        self._pending_ts_col = self._settings_int(self._settings.value("waterfall/ts_col"), self.ts_col.value())

        self.energy_win.setValue(
            self._settings_int(self._settings.value("transform/energy_win"), self.energy_win.value())
        )
        self.db_vmin.setValue(
            self._settings_float(self._settings.value("transform/db_vmin"), self.db_vmin.value())
        )
        self.db_vmax.setValue(
            self._settings_float(self._settings.value("transform/db_vmax"), self.db_vmax.value())
        )
        self.gamma.setValue(
            self._settings_float(self._settings.value("transform/gamma"), self.gamma.value())
        )
        self.eps.setValue(
            self._settings_float(self._settings.value("transform/eps"), self.eps.value())
        )
        self.invert.setChecked(
            self._settings_bool(self._settings.value("transform/invert"), self.invert.isChecked())
        )

        saved_mode = str(self._settings.value("recording/mode", self.record_mode.currentData()))
        mode_index = self.record_mode.findData(saved_mode)
        if mode_index >= 0:
            self.record_mode.setCurrentIndex(mode_index)
        saved_scope = str(self._settings.value("recording/scope", self.record_scope.currentData()))
        scope_index = self.record_scope.findData(saved_scope)
        if scope_index >= 0:
            self.record_scope.setCurrentIndex(scope_index)

        output_dir = str(self._settings.value("recording/output_dir", str(self.recording_service.output_root)))
        self.record_output_dir.setText(output_dir)
        self.recording_service.set_output_root(output_dir)
        self._sync_waterfall_history(clear=False)
        self._update_wf_range_status()

        self._reset_fibre_break_detector()

    def _poke_refresh(self, *args):
        self._last_update_ts = 0.0

    def _selected_stream(self) -> tuple[int, str]:
        try:
            sel_ch = int(self.wf_channel.currentText())
        except Exception:
            sel_ch = 1
        sel_kind = self.wf_kind.currentText() or "phase"
        return sel_ch, sel_kind

    def _recording_scope(self) -> str:
        return str(self.record_scope.currentData() or "full")

    def _spacing_m(self, scale_down: int | None = None) -> float:
        return DistanceAxis.base_spacing_m() * max(1, int(self._wf_scale_down if scale_down is None else scale_down))

    def _absolute_col(self, local_col: int) -> int:
        return max(0, int(self._wf_data_start_col) + max(0, int(local_col)))

    def _current_range_filter_state(
        self,
        point_count: int | None = None,
        scale_down: int | None = None,
    ) -> dict:
        total_cols = max(0, int(self._wf_source_point_count if point_count is None else point_count))
        spacing_m = self._spacing_m(scale_down)
        enabled = bool(self.wf_range_enabled.isChecked()) and total_cols > 0
        full_end_m = max(0.0, (total_cols - 1) * spacing_m) if total_cols > 0 else 0.0
        if not enabled:
            return {
                "enabled": False,
                "start_m": 0.0,
                "end_m": full_end_m,
                "start_col": 0,
                "end_col": total_cols,
                "source_point_count": total_cols,
                "filtered_point_count": total_cols,
            }

        start_m = max(0.0, float(self.wf_range_start_m.value()))
        end_m = max(0.0, float(self.wf_range_end_m.value()))
        if end_m < start_m:
            start_m, end_m = end_m, start_m

        if total_cols <= 1:
            return {
                "enabled": True,
                "start_m": start_m,
                "end_m": end_m,
                "start_col": 0,
                "end_col": min(1, total_cols),
                "source_point_count": total_cols,
                "filtered_point_count": min(1, total_cols),
            }

        start_col = int(np.floor(start_m / spacing_m))
        end_col = int(np.ceil(end_m / spacing_m)) + 1
        start_col = max(0, min(start_col, total_cols - 1))
        end_col = max(start_col + 1, min(end_col, total_cols))
        return {
            "enabled": True,
            "start_m": start_m,
            "end_m": end_m,
            "start_col": start_col,
            "end_col": end_col,
            "source_point_count": total_cols,
            "filtered_point_count": max(0, end_col - start_col),
        }

    def _current_range_text(self, range_state: dict | None = None, scale_down: int | None = None) -> str:
        state = self._current_range_filter_state() if range_state is None else range_state
        spacing_m = self._spacing_m(scale_down)
        if not state["enabled"]:
            if state["source_point_count"] > 0:
                end_distance = max(0.0, (state["source_point_count"] - 1) * spacing_m)
                return f"Full Range: 0 m - {self.distance_axis._format_distance(end_distance)}"
            return "Full Range"
        start_distance = state["start_col"] * spacing_m
        end_distance = max(start_distance, (state["end_col"] - 1) * spacing_m)
        return (
            f"Filtered Range: {self.distance_axis._format_distance(start_distance)}"
            f" - {self.distance_axis._format_distance(end_distance)}"
        )

    def _update_wf_range_status(self, point_count: int | None = None, scale_down: int | None = None):
        self.wf_range_status.setText(
            f"Range Filter: {self._current_range_text(self._current_range_filter_state(point_count, scale_down), scale_down=scale_down)}"
        )

    def _apply_wf_range_filter(self, payload: dict) -> tuple[dict, dict]:
        point_count = int(payload.get("point_count", 0) or 0)
        if point_count <= 0:
            return payload, self._current_range_filter_state(point_count=0, scale_down=int(payload.get("cfg_scale_down", 1) or 1))

        scale_down = int(payload.get("cfg_scale_down", self.scale_down.value()) or self.scale_down.value())
        range_state = self._current_range_filter_state(point_count=point_count, scale_down=scale_down)
        start_col = int(range_state["start_col"])
        end_col = int(range_state["end_col"])
        if start_col <= 0 and end_col >= point_count:
            if not range_state["enabled"]:
                return payload, range_state
            passthrough = dict(payload)
            passthrough["range_filter"] = {
                "enabled": bool(range_state["enabled"]),
                "start_m": float(range_state["start_m"]),
                "end_m": float(range_state["end_m"]),
                "start_col": start_col,
                "end_col": end_col,
                "source_point_count": int(range_state["source_point_count"]),
                "filtered_point_count": int(range_state["filtered_point_count"]),
            }
            return passthrough, range_state

        block = np.asarray(payload["block"], dtype=np.float32)
        cropped = dict(payload)
        cropped["block"] = np.array(block[:, start_col:end_col], dtype=np.float32, copy=True)
        cropped["point_count"] = int(cropped["block"].shape[1])
        cropped["range_filter"] = {
            "enabled": bool(range_state["enabled"]),
            "start_m": float(range_state["start_m"]),
            "end_m": float(range_state["end_m"]),
            "start_col": start_col,
            "end_col": end_col,
            "source_point_count": int(range_state["source_point_count"]),
            "filtered_point_count": int(range_state["filtered_point_count"]),
        }
        return cropped, range_state

    def _on_wf_range_changed(self, *args):
        self._update_wf_range_status()
        self._clear_selected_stream_view()
        self._poke_refresh()

    def _history_lines_per_row(self, scan_rate_label: str) -> int:
        hz = self._parse_scan_rate_hz(scan_rate_label)
        if hz <= 0.0:
            hz = 1000.0
        target_s = max(0.1, float(self.wf_history_seconds.value()))
        return max(1, int(np.ceil(target_s * hz / max(1, int(self.renderer.wf_height)))))

    def _effective_history_seconds(self, scan_rate_label: str, lines_per_row: int | None = None) -> float:
        hz = self._parse_scan_rate_hz(scan_rate_label)
        if hz <= 0.0:
            hz = 1000.0
        lpr = max(1, int(self.renderer.lines_per_row if lines_per_row is None else lines_per_row))
        return float(self.renderer.wf_height) * float(lpr) / float(hz)

    def _sync_waterfall_history(self, scan_rate_label: str | None = None, clear: bool = True):
        scan_label = str(scan_rate_label or self.scan_rate.currentText() or "1k")
        self._wf_history_target_s = max(0.1, float(self.wf_history_seconds.value()))
        lines_per_row = self._history_lines_per_row(scan_label)
        self._wf_history_effective_s = self._effective_history_seconds(scan_label, lines_per_row=lines_per_row)
        changed = self.renderer.set_lines_per_row(lines_per_row)
        if changed and clear:
            self._clear_selected_stream_view()
            sel_ch, sel_kind = self._selected_stream()
            self.status.setText(
                f"Status: Waiting for ch{sel_ch}/{sel_kind} data "
                f"(history~{self._wf_history_effective_s:.2f}s)"
            )

    def _on_wf_history_changed(self, *args):
        self._sync_waterfall_history()
        self._poke_refresh()

    def _clear_selected_stream_view(self):
        self._clear_timeseries_cache()
        self._ts_last_t = 0.0
        self._ts_series.clear()
        self.renderer.clear()
        self._wf_src_w = 0
        self._wf_src_h = 0
        self._wf_source_point_count = 0
        self._wf_data_start_col = 0
        self._wf_data_source_end_col = 0
        self._wf_view_start_col = 0
        self._wf_view_col_count = 0
        self.display.clear()
        self.display.setText("Waiting for selected stream...")
        self.display.setToolTip("")
        self.hover_info.setText("Hover waterfall to inspect point")
        self._last_update_ts = 0.0
        self._update_ts_title()
        self._update_distance_axis_from_ui()

    def _on_stream_selection_changed(self, *args):
        self._clear_selected_stream_view()
        sel_ch, sel_kind = self._selected_stream()
        self.status.setText(f"Status: Waiting for ch{sel_ch}/{sel_kind} data")

    def _selected_break_monitor_channel(self) -> int:
        try:
            return int(self.break_monitor_channel.currentText())
        except Exception:
            return 1

    def _sync_switch_state_from_ui(self):
        self.switch_service.set_assumed_fibres(
            self._combo_fibre_name(self.switch_ch1),
            self._combo_fibre_name(self.switch_ch2),
        )
        self._refresh_switch_status()
        self._update_api_snapshot()

    def _sync_fibre_break_detector_config(self):
        self.fibre_monitor.configure(
            monitor_channel=self._selected_break_monitor_channel(),
            spatial_ewma_alpha=float(self.break_alpha.value()),
            threshold=float(self.break_threshold.value()),
            min_length_m=float(self.break_min_length.value()),
            default_fibre=self._combo_fibre_name(self.break_default_fibre),
            enable_alarm=bool(self.break_enable_alarm.isChecked()),
            enable_autoswitch=bool(self.break_enable_autoswitch.isChecked()),
            enable_peek=bool(self.break_enable_peek.isChecked()),
            peek_interval=int(self.break_peek_interval.value()),
            peek_delay_ms=int(self.break_peek_delay_ms.value()),
        )

    def _reset_fibre_break_detector(self, *args):
        self._sync_fibre_break_detector_config()
        self.fibre_monitor.reset()
        self._update_fibre_break_status()

    def _format_length_text(self, distance_m: float) -> str:
        if not np.isfinite(distance_m) or distance_m < 0.0:
            return "n/a"
        return self.distance_axis._format_distance(distance_m)

    def _update_fibre_break_status(self, *args):
        self._sync_fibre_break_detector_config()
        status_view = self.fibre_monitor.status_view(
            current_fibres=self.switch_service.snapshot(),
            display_name=self._display_fibre_name,
            format_length=self._format_length_text,
        )
        self.break_status.setText(status_view.text)
        if status_view.alarm:
            self.break_status.setStyleSheet("color: #b00020; font-weight: bold;")
        else:
            self.break_status.setStyleSheet("")
        self._update_api_snapshot()

    def _set_switch_combo_for_channel(self, channel: int, fibre_name: str):
        combo = self.switch_ch1 if int(channel) == 1 else self.switch_ch2
        self._set_combo_text(combo, self._display_fibre_name(fibre_name))

    def _refresh_switch_status(self, detail: str | None = None):
        ch1 = self._display_fibre_name(self.switch_service.current_fibre(1))
        ch2 = self._display_fibre_name(self.switch_service.current_fibre(2))
        if self.switch_service.is_open:
            text = f"Switch: Connected @ {self.switch_service.port_name}, CH1={ch1}, CH2={ch2}"
        else:
            text = f"Switch: Disconnected, CH1={ch1}, CH2={ch2}"
        if detail:
            text = f"{text}. {detail}"
        self.switch_status.setText(text)
        self._update_api_snapshot()

    def _update_fibre_break_from_payload(self, payload: dict):
        self._sync_fibre_break_detector_config()
        actions = self.fibre_monitor.process_amp_payload(
            payload=payload,
            current_fibres=self.switch_service.snapshot(),
            switch_connected=self.switch_service.is_open,
        )
        for action in actions:
            try:
                self.switch_service.set_fibre(action.channel, action.fibre_name)
                self._set_switch_combo_for_channel(action.channel, action.fibre_name)
                self._refresh_switch_status(
                    action.detail.replace(action.fibre_name, self._display_fibre_name(action.fibre_name))
                )
            except Exception as e:
                reason = "Auto switch" if action.reason == "auto_switch" else "Peek"
                self.switch_status.setText(f"Switch: {reason} failed: {e}")
                break
        self._update_fibre_break_status()

    def _update_distance_axis_from_ui(self, *args):
        self._clamp_viewport()
        self.distance_axis.set_axis_state(
            point_count=int(self._wf_source_point_count or self._wf_src_w or 0),
            scale_down=int(self._wf_scale_down or self.scale_down.value()),
            selected_col=int(self._absolute_col(self.ts_col.value())),
            view_start_col=int(self._wf_data_start_col + self._wf_view_start_col),
            view_point_count=int(self._effective_view_col_count()),
        )
        self._update_wf_range_status(
            point_count=int(self._wf_source_point_count or self._wf_src_w or 0),
            scale_down=int(self._wf_scale_down or self.scale_down.value()),
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
        abs_col = self._absolute_col(col)
        distance_m = abs_col * DistanceAxis.base_spacing_m() * max(1, int(scale_down))
        return f"col={abs_col}, dist={self.distance_axis._format_distance(distance_m)}"

    def _current_column_distance_label(self, point_count: int, scale_down: int) -> str:
        if point_count <= 0:
            return "column 0"

        col = min(max(0, int(self.ts_col.value())), point_count - 1)
        abs_col = self._absolute_col(col)
        distance_m = abs_col * DistanceAxis.base_spacing_m() * max(1, int(scale_down))
        return f"column {abs_col} ({self.distance_axis._format_distance(distance_m)})"

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

    def _recording_mode(self) -> str:
        return str(self.record_mode.currentData() or "selected")

    def _recording_output_dir(self) -> str:
        return (self.record_output_dir.text() or "").strip()

    def _refresh_recording_status(self):
        self.record_status.setText(self.recording_service.status_text())

    @staticmethod
    def _format_local_datetime(epoch_s: float) -> str:
        if not np.isfinite(epoch_s):
            return "n/a"
        whole = int(epoch_s)
        ms = int(round((epoch_s - whole) * 1000.0))
        if ms >= 1000:
            whole += 1
            ms = 0
        return f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(whole))}.{ms:03d}"

    @staticmethod
    def _format_utc_datetime(epoch_s: float) -> str:
        if not np.isfinite(epoch_s):
            return "n/a"
        whole = int(epoch_s)
        ms = int(round((epoch_s - whole) * 1000.0))
        if ms >= 1000:
            whole += 1
            ms = 0
        return f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(whole))}.{ms:03d} UTC"

    def _update_clock_label(self):
        now = time.time()
        self.clock_label.setText(
            f"Time: Local {self._format_local_datetime(now)} | UTC {self._format_utc_datetime(now)}"
        )

    def _recording_metadata(self) -> dict:
        sel_ch, sel_kind = self._selected_stream()
        range_state = self._current_range_filter_state()
        return {
            "machine_id": self.machine_id,
            "selected_stream": {
                "channel": int(sel_ch),
                "kind": str(sel_kind),
            },
            "acquisition": {
                "scan_rate": self.scan_rate.currentText(),
                "mode": self.mode.currentText(),
                "pulse_width": int(self.pulse_width.value()),
                "scale_down": int(self.scale_down.value()),
            },
            "transform": {
                "mode": str(self.transform.mode),
                "energy_win": int(self.energy_win.value()),
                "vmin": float(self.db_vmin.value()),
                "vmax": float(self.db_vmax.value()),
                "gamma": float(self.gamma.value()),
                "eps": float(self.eps.value()),
                "invert": bool(self.invert.isChecked()),
            },
            "waterfall": {
                "history_seconds_target": float(self._wf_history_target_s),
                "history_seconds_effective": float(self._wf_history_effective_s),
                "history_lines_per_row": int(self.renderer.lines_per_row),
                "history_rows": int(self.renderer.wf_height),
                "range_filter_enabled": bool(range_state["enabled"]),
                "range_start_m": float(range_state["start_m"]),
                "range_end_m": float(range_state["end_m"]),
                "range_start_col": int(range_state["start_col"]),
                "range_end_col": int(range_state["end_col"]),
                "source_point_count": int(range_state["source_point_count"]),
                "filtered_point_count": int(range_state["filtered_point_count"]),
            },
            "recording_scope": str(self._recording_scope()),
        }

    def _snapshot_metadata(self) -> dict:
        sel_ch, sel_kind = self._selected_stream()
        now = time.time()
        range_state = self._current_range_filter_state()
        return {
            **self._recording_metadata(),
            "saved_at_epoch_s": now,
            "saved_at_local": self._format_local_datetime(now),
            "saved_at_utc": self._format_utc_datetime(now),
            "waterfall": {
                "channel": int(sel_ch),
                "kind": str(sel_kind),
                "source_width": int(self._wf_src_w or 0),
                "source_height": int(self._wf_src_h or 0),
                "view_start_col": int(self._wf_view_start_col),
                "view_col_count": int(self._effective_view_col_count()),
                "absolute_view_start_col": int(self._wf_data_start_col + self._wf_view_start_col),
                "scale_down": int(self._wf_scale_down or self.scale_down.value()),
                "ts_col": int(self.ts_col.value()),
                "absolute_ts_col": int(self._absolute_col(self.ts_col.value())),
                "history_seconds_target": float(self._wf_history_target_s),
                "history_seconds_effective": float(self._wf_history_effective_s),
                "history_lines_per_row": int(self.renderer.lines_per_row),
                "history_rows": int(self.renderer.wf_height),
                "range_filter_enabled": bool(range_state["enabled"]),
                "range_start_m": float(range_state["start_m"]),
                "range_end_m": float(range_state["end_m"]),
                "range_start_col": int(range_state["start_col"]),
                "range_end_col": int(range_state["end_col"]),
                "source_point_count": int(range_state["source_point_count"]),
                "filtered_point_count": int(range_state["filtered_point_count"]),
            },
        }

    def on_wf_range_use_view_clicked(self):
        total_cols = int(self._wf_src_w or 0)
        if total_cols <= 0:
            return
        spacing_m = self._spacing_m()
        abs_start = int(self._wf_data_start_col + self._wf_view_start_col)
        abs_end = int(abs_start + self._effective_view_col_count() - 1)
        self.wf_range_enabled.setChecked(True)
        self.wf_range_start_m.setValue(abs_start * spacing_m)
        self.wf_range_end_m.setValue(max(abs_start * spacing_m, abs_end * spacing_m))
        self._on_wf_range_changed()

    def on_wf_range_reset_clicked(self):
        self.wf_range_enabled.setChecked(False)
        self.wf_range_start_m.setValue(0.0)
        total_cols = int(self._wf_source_point_count or self._wf_src_w or 0)
        end_distance = max(0.0, (total_cols - 1) * self._spacing_m()) if total_cols > 0 else 0.0
        self.wf_range_end_m.setValue(end_distance)
        self._on_wf_range_changed()

    def on_record_browse_clicked(self):
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Recording Output Folder",
            self._recording_output_dir() or str(self.recording_service.output_root),
        )
        if not selected_dir:
            return
        self.record_output_dir.setText(selected_dir)
        self.recording_service.set_output_root(selected_dir)
        self._refresh_recording_status()

    def on_record_open_clicked(self):
        target_dir = self.recording_service.session_dir()
        if target_dir is None:
            target_dir = self.recording_service.output_root
        target_dir = target_dir.expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir))):
            QMessageBox.warning(
                self,
                "Recording Folder",
                f"Failed to open folder:\n{target_dir}",
            )

    def on_record_start_clicked(self):
        try:
            self.recording_service.set_output_root(self._recording_output_dir() or self.recording_service.output_root)
            session_dir = self.recording_service.start_recording(
                mode=self._recording_mode(),
                metadata=self._recording_metadata(),
            )
            self._refresh_recording_status()
            self.status.setText(f"Status: Recording started @ {session_dir}")
        except Exception as e:
            QMessageBox.warning(self, "Recording", f"Failed to start recording:\n{e}")
            self._refresh_recording_status()

    def on_record_stop_clicked(self):
        try:
            self.recording_service.stop_recording()
            self._refresh_recording_status()
            self.status.setText("Status: Recording stopped")
        except Exception as e:
            QMessageBox.warning(self, "Recording", f"Failed to stop recording:\n{e}")
            self._refresh_recording_status()

    def on_save_snapshot_clicked(self):
        try:
            pixmap = self.display.pixmap()
            snapshot_path = self.recording_service.save_snapshot(
                pixmap=pixmap,
                values=self.renderer.values,
                row_times=self.renderer.row_times,
                metadata=self._snapshot_metadata(),
            )
            self._refresh_recording_status()
            self.status.setText(f"Status: Snapshot saved @ {snapshot_path}")
        except Exception as e:
            QMessageBox.warning(self, "Save Snapshot", f"Failed to save snapshot:\n{e}")
            self._refresh_recording_status()

    def _ensure_docs_dialog(self, dialog_key: str, title: str) -> tuple[QDialog, QTextBrowser]:
        existing = self._docs_dialogs.get(dialog_key)
        if existing is not None:
            return existing

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(920, 760)

        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser)

        close_button = QPushButton("Close", dialog)
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button, 0, Qt.AlignRight)

        self._docs_dialogs[dialog_key] = (dialog, browser)
        return dialog, browser

    def _show_markdown_document(self, doc_name: str, title: str, dialog_key: str):
        docs_path = self.docs_service.path_for(doc_name)
        if not docs_path.exists():
            QMessageBox.warning(
                self,
                title,
                f"Documentation file not found:\n{docs_path}",
            )
            return

        try:
            markdown_text = self.docs_service.read_markdown(doc_name)
        except Exception as e:
            QMessageBox.warning(
                self,
                title,
                f"Failed to read documentation:\n{e}",
            )
            return

        dialog, browser = self._ensure_docs_dialog(dialog_key, title)
        browser.setMarkdown(markdown_text)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def on_api_docs_clicked(self):
        self._show_markdown_document(
            "api.md",
            "API Documentation",
            "api_docs",
        )

    def on_user_guide_clicked(self):
        self._show_markdown_document(
            "user_guide.md",
            "User Guide",
            "user_guide",
        )

    def _refresh_switch_ports(self):
        current_text = (self.switch_port.currentText() or "").strip()
        ports = self.switch_service.available_ports()

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
            self.switch_service.open(port_name)
            self._sync_switch_state_from_ui()
            self._refresh_switch_status()
        except Exception as e:
            self.switch_status.setText(f"Switch: Connect failed: {e}")

    def on_switch_disconnect_clicked(self):
        try:
            self.switch_service.close()
            self.fibre_monitor.cancel_peek(reset_counter=True)
            self._refresh_switch_status()
        except Exception as e:
            self.switch_status.setText(f"Switch: Disconnect failed: {e}")

    def on_switch_apply_clicked(self):
        try:
            ch1_fibre = self._combo_fibre_name(self.switch_ch1)
            ch2_fibre = self._combo_fibre_name(self.switch_ch2)
            self.switch_service.set_fibres(ch1_fibre, ch2_fibre)
            self.fibre_monitor.cancel_peek(reset_counter=True)
            self._refresh_switch_status("Applied manual fibre selection")
            self._update_fibre_break_status()
        except Exception as e:
            self.switch_status.setText(f"Switch: Apply failed: {e}")

    def on_data_ready(self, payload: dict):
        try:
            ch = int(payload.get("channel", 1))
            kind = str(payload.get("kind", "phase"))
            self._latest_by_stream[(ch, kind)] = payload
            recording_payload = payload
            if self._recording_scope() == "filtered":
                recording_payload, _ = self._apply_wf_range_filter(payload)
            self.recording_service.handle_payload(recording_payload, selected_stream=self._selected_stream())
            self._update_fibre_break_from_payload(payload)
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
        abs_col = self._absolute_col(col)
        distance_m = abs_col * DistanceAxis.base_spacing_m() * max(1, int(self._wf_scale_down))
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
            f"row={row}, col={abs_col}"
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
            if self._pending_ts_col is not None:
                restored_col = min(max(0, int(self._pending_ts_col)), max(0, point_count - 1))
                self.ts_col.setValue(restored_col)
                col = restored_col
                self._pending_ts_col = None
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
        self._refresh_recording_status()
        self._update_clock_label()
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

            if point_count <= 0 or num_lines <= 0:
                return

            block = np.asarray(block, dtype=np.float32)
            if block.ndim != 2 or block.shape[1] != point_count:
                block = block.reshape((-1, point_count))
                num_lines = block.shape[0]
                if num_lines <= 0:
                    return

            original_point_count = int(point_count)
            self._wf_source_point_count = int(original_point_count)
            payload_for_display, range_state = self._apply_wf_range_filter(
                {
                    **payload,
                    "block": block,
                    "point_count": original_point_count,
                    "cb_lines": num_lines,
                }
            )
            block = np.asarray(payload_for_display["block"], dtype=np.float32)
            point_count = int(payload_for_display["point_count"])
            self._wf_data_start_col = int(range_state["start_col"])
            self._wf_data_source_end_col = max(self._wf_data_start_col, int(range_state["end_col"]) - 1)
            self._last_point_count_for_click = point_count

            self._update_timeseries_from_block(block, cfg_scan, point_count)
            self._sync_transform_params()

            prev_point_count = int(self._wf_src_w or 0)
            was_full_view = prev_point_count <= 0 or self._effective_view_col_count(prev_point_count) >= prev_point_count
            self._sync_waterfall_history(cfg_scan, clear=False)
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
                f"hist~{self._wf_history_effective_s:.2f}s, lpr={self.renderer.lines_per_row}, "
                f"lines={num_lines}, points={point_count}/{original_point_count}, "
                f"range={self._current_range_text(range_state, scale_down=sd)}, "
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

    def _update_api_snapshot(self):
        self._sync_fibre_break_detector_config()
        snapshot = self.fibre_monitor.build_api_snapshot(
            machine_id=self.machine_id,
            current_fibres=self.switch_service.snapshot(),
        )
        with self._api_snapshot_lock:
            self._api_snapshot = snapshot
        self.compat_api.set_snapshot(snapshot)

    def _get_api_snapshot(self) -> dict:
        with self._api_snapshot_lock:
            return dict(self._api_snapshot)

    def closeEvent(self, event):
        try:
            self._save_settings()
        except Exception:
            pass
        try:
            self.worker.stop()
        except Exception:
            pass
        try:
            self.recording_service.stop_recording()
        except Exception:
            pass
        try:
            self.switch_service.close()
        except Exception:
            pass
        try:
            self.compat_api.stop()
        except Exception:
            pass
        event.accept()
