import time
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QScrollArea
)

from backend.acquisition import AcquisitionWorker
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

        # Stream selection
        self.wf_channel = QComboBox()
        self.wf_channel.addItems(["1", "2"])
        self.wf_kind = QComboBox()
        self.wf_kind.addItems(["phase", "amp"])

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
        self.invert.setChecked(True)

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
        control_layout.addWidget(QLabel("Waterfall Channel"))
        control_layout.addWidget(self.wf_channel)
        control_layout.addWidget(QLabel("Waterfall Kind"))
        control_layout.addWidget(self.wf_kind)

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

        # ---- Right display ----
        self.display = QLabel("Waterfall Display")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setStyleSheet("background-color: black; color: white;")
        self.display.setMinimumSize(800, 600)

        # ---- Put controls into a scroll area ----
        control_widget = QWidget()
        control_widget.setLayout(control_layout)

        scroll = QScrollArea()
        scroll.setWidget(control_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(280)

        main_layout.addWidget(scroll, 0)
        main_layout.addWidget(self.display, 1)

        # ---- Worker ----
        self.worker = AcquisitionWorker()
        self.worker.data_ready.connect(self.on_data_ready)

        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)

        # ---- Data cache ----
        self._latest_by_stream = {}  # (ch, kind) -> payload

        # ---- UI refresh throttling ----
        self._last_update_ts = 0.0
        self._min_ui_interval = 1.0 / 30.0  # 30 FPS

        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / 30))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # When selection/params change, allow next tick immediately
        self.wf_channel.currentIndexChanged.connect(self._poke_refresh)
        self.wf_kind.currentIndexChanged.connect(self._poke_refresh)
        self.energy_win.valueChanged.connect(self._poke_refresh)
        self.db_vmin.valueChanged.connect(self._poke_refresh)
        self.db_vmax.valueChanged.connect(self._poke_refresh)
        self.gamma.valueChanged.connect(self._poke_refresh)
        self.eps.valueChanged.connect(self._poke_refresh)
        self.invert.stateChanged.connect(self._poke_refresh)

    def _poke_refresh(self, *args):
        self._last_update_ts = 0.0

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

    def on_data_ready(self, payload: dict):
        try:
            ch = int(payload.get("channel", 1))
            kind = str(payload.get("kind", "phase"))
            self._latest_by_stream[(ch, kind)] = payload
        except Exception:
            pass

    def _pull_selected_payload(self):
        try:
            sel_ch = int(self.wf_channel.currentText())
        except Exception:
            sel_ch = 1
        sel_kind = self.wf_kind.currentText() or "phase"
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
            sd = payload.get("cfg_scale_down", "")

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

            self._sync_transform_params()

            self.renderer.ensure(point_count)
            if self.renderer.wf is None:
                return

            gray_block = self.transform.apply(block)
            self.renderer.push_block(gray_block)
            self.renderer.render_to_label(self.display)

            self.status.setText(
                f"Status: Running (show=ch{sel_ch}/{sel_kind}, tf=Energy(MSE dB), "
                f"win={self.transform.energy_win}, dB=({self.transform.vmin:.1f},{self.transform.vmax:.1f}), "
                f"gamma={self.transform.gamma:.2f}, "
                f"cfg_scan={cfg_scan}, mode={cfg_mode}, pw={pw}, sd={sd}, "
                f"lines={num_lines}, points={point_count})"
            )

        except Exception as e:
            self.status.setText(f"Status: Render error: {e}")

    def closeEvent(self, event):
        try:
            self.worker.stop()
        except Exception:
            pass
        event.accept()