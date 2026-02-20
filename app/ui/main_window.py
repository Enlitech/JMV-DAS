import time
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox
)

from backend.acquisition import AcquisitionWorker
from ..transformers.waterfall_transform import WaterfallTransform
from ..viz.waterfall_renderer import WaterfallRenderer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("JMV-DAS Infrastructure Secure")
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout()
        central.setLayout(main_layout)

        # ---- Left controls ----
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
        self.wf_kind.addItems(["amp", "phase"])

        # Transform params
        self.tf_mode = QComboBox()
        self.tf_mode.addItems(["Linear", "Abs", "Log(dB)", "HP(MeanRemove)"])

        self.tf_p_lo = QDoubleSpinBox()
        self.tf_p_lo.setRange(0.0, 100.0)
        self.tf_p_lo.setDecimals(1)
        self.tf_p_lo.setSingleStep(1.0)
        self.tf_p_lo.setValue(5.0)

        self.tf_p_hi = QDoubleSpinBox()
        self.tf_p_hi.setRange(0.0, 100.0)
        self.tf_p_hi.setDecimals(1)
        self.tf_p_hi.setSingleStep(1.0)
        self.tf_p_hi.setValue(95.0)

        self.tf_gamma = QDoubleSpinBox()
        self.tf_gamma.setRange(0.1, 5.0)
        self.tf_gamma.setDecimals(2)
        self.tf_gamma.setSingleStep(0.05)
        self.tf_gamma.setValue(1.0)

        self.tf_eps = QDoubleSpinBox()
        self.tf_eps.setRange(1e-12, 1.0)
        self.tf_eps.setDecimals(12)
        self.tf_eps.setSingleStep(1e-6)
        self.tf_eps.setValue(1e-6)

        self.tf_invert = QCheckBox("Invert (background bright)")
        self.tf_invert.setChecked(True)

        # Buttons
        self.btn_open = QPushButton("Open (noop)")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")

        self.status = QLabel("Status: Idle")
        self.status.setWordWrap(True)

        # Layout
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
        control_layout.addWidget(QLabel("Transform"))
        control_layout.addWidget(self.tf_mode)
        control_layout.addWidget(QLabel("Percentile Lo"))
        control_layout.addWidget(self.tf_p_lo)
        control_layout.addWidget(QLabel("Percentile Hi"))
        control_layout.addWidget(self.tf_p_hi)
        control_layout.addWidget(QLabel("Gamma"))
        control_layout.addWidget(self.tf_gamma)
        control_layout.addWidget(QLabel("Eps (for Log)"))
        control_layout.addWidget(self.tf_eps)
        control_layout.addWidget(self.tf_invert)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.btn_open)
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.status)
        control_layout.addStretch()

        # ---- Right display ----
        self.display = QLabel("Waterfall Display")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setStyleSheet("background-color: black; color: white;")
        self.display.setMinimumSize(800, 600)

        main_layout.addLayout(control_layout, 0)
        main_layout.addWidget(self.display, 1)

        # ---- Worker ----
        self.worker = AcquisitionWorker()
        self.worker.data_ready.connect(self.on_data_ready)

        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_open.clicked.connect(self.on_open_clicked)

        # ---- Data cache ----
        self._latest_by_stream = {}  # (ch, kind) -> payload

        # ---- Transform/Renderer ----
        self.transform = WaterfallTransform()
        self.renderer = WaterfallRenderer(wf_height=600)

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
        self.tf_mode.currentIndexChanged.connect(self._poke_refresh)
        self.tf_p_lo.valueChanged.connect(self._poke_refresh)
        self.tf_p_hi.valueChanged.connect(self._poke_refresh)
        self.tf_gamma.valueChanged.connect(self._poke_refresh)
        self.tf_eps.valueChanged.connect(self._poke_refresh)
        self.tf_invert.stateChanged.connect(self._poke_refresh)

    def _poke_refresh(self, *args):
        self._last_update_ts = 0.0

    def on_open_clicked(self):
        self.status.setText("Status: Open is noop (Start will open).")

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
            kind = str(payload.get("kind", "amp"))
            self._latest_by_stream[(ch, kind)] = payload
        except Exception:
            pass

    def _pull_selected_payload(self):
        try:
            sel_ch = int(self.wf_channel.currentText())
        except Exception:
            sel_ch = 1
        sel_kind = self.wf_kind.currentText() or "amp"
        key = (sel_ch, sel_kind)
        payload = self._latest_by_stream.get(key)
        if payload is None:
            return None, sel_ch, sel_kind
        self._latest_by_stream.pop(key, None)
        return payload, sel_ch, sel_kind

    def _sync_transform_params(self):
        self.transform.mode = self.tf_mode.currentText()
        self.transform.p_lo = float(self.tf_p_lo.value())
        self.transform.p_hi = float(self.tf_p_hi.value())
        self.transform.gamma = float(self.tf_gamma.value())
        self.transform.eps = float(self.tf_eps.value())
        self.transform.invert = bool(self.tf_invert.isChecked())

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
                f"Status: Running (show=ch{sel_ch}/{sel_kind}, tf={self.transform.mode}, "
                f"p=({self.transform.p_lo:.1f},{self.transform.p_hi:.1f}), gamma={self.transform.gamma:.2f}, "
                f"cfg_scan={cfg_scan}, mode={cfg_mode}, pw={pw}, sd={sd}, lines={num_lines}, points={point_count})"
            )

        except Exception as e:
            self.status.setText(f"Status: Render error: {e}")

    def closeEvent(self, event):
        try:
            self.worker.stop()
        except Exception:
            pass
        event.accept()