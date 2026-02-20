import sys
import time
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox
)

from backend.acquisition import AcquisitionWorker


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

        # ---- Waterfall selector ----
        self.wf_channel = QComboBox()
        self.wf_channel.addItems(["1", "2"])
        self.wf_kind = QComboBox()
        self.wf_kind.addItems(["amp", "phase"])

        self.btn_open = QPushButton("Open (noop)")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")

        self.status = QLabel("Status: Idle")
        self.status.setWordWrap(True)

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

        # ---- Waterfall buffer ----
        self.wf_width = None
        self.wf_height = 600
        self.wf = None  # uint8[H,W]

        # 每个 stream 一份最新数据，避免 4 路互相覆盖
        # key: (channel:int, kind:str) -> payload
        self._latest_by_stream = {}

        # UI 刷新频率限制
        self._last_update_ts = 0.0
        self._min_ui_interval = 1.0 / 30.0  # 30 FPS

        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / 30))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # 视觉：背景亮、事件暗（通常要反相）
        self.invert = True

        # 切换选择时，让界面尽快刷新（不用等到下个数据）
        self.wf_channel.currentIndexChanged.connect(self._poke_refresh)
        self.wf_kind.currentIndexChanged.connect(self._poke_refresh)

    def _poke_refresh(self):
        # 让 tick 允许立刻刷新一次
        self._last_update_ts = 0.0

    def on_open_clicked(self):
        self.status.setText("Status: Open is noop (Start will open).")

    def on_start_clicked(self):
        try:
            scan_rate_label = self.scan_rate.currentText()   # "1k/2k/4k/10k"
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
        """
        payload expected keys:
          cfg_scan_rate, cfg_mode, cfg_pulse_width, cfg_scale_down,
          channel, kind, cb_lines, point_count, block
        """
        try:
            ch = int(payload.get("channel", 1))
            kind = str(payload.get("kind", "amp"))
            self._latest_by_stream[(ch, kind)] = payload
        except Exception:
            # 防御性：不让 UI 因 payload 异常崩掉
            pass

    def _ensure_waterfall(self, width: int):
        width = int(width)
        if width <= 0:
            return
        if self.wf is not None and self.wf_width == width:
            return
        self.wf_width = width
        self.wf = np.zeros((self.wf_height, self.wf_width), dtype=np.uint8)
        self.status.setText(f"Status: Waterfall resized to {self.wf_width}x{self.wf_height}")

    def _tick(self):
        # 当前选择的 stream
        try:
            sel_ch = int(self.wf_channel.currentText())
        except Exception:
            sel_ch = 1
        sel_kind = self.wf_kind.currentText() or "amp"

        key = (sel_ch, sel_kind)
        payload = self._latest_by_stream.get(key)
        if payload is None:
            return

        now = time.time()
        if now - self._last_update_ts < self._min_ui_interval:
            return
        self._last_update_ts = now

        # 消费掉这一帧（只处理最新帧）
        self._latest_by_stream.pop(key, None)

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
                # 防御性处理
                block = block.reshape((-1, point_count))
                num_lines = block.shape[0]
                if num_lines <= 0:
                    return

            self._ensure_waterfall(point_count)
            if self.wf is None:
                return

            # ---- 把 block 映射成 uint8 灰度（对整个 block 做一次 scaling）----
            x = block

            # robust scaling：按 block 的分位数，避免偶发强点把对比度毁掉
            lo = np.percentile(x, 5)
            hi = np.percentile(x, 95)
            if not np.isfinite(lo) or not np.isfinite(hi) or (hi - lo) < 1e-12:
                lo = float(np.nanmin(x))
                hi = float(np.nanmax(x)) + 1e-6

            x = (x - lo) / (hi - lo)
            x = np.clip(x, 0.0, 1.0)

            if self.invert:
                gray_block = ((1.0 - x) * 255.0).astype(np.uint8)
            else:
                gray_block = (x * 255.0).astype(np.uint8)

            # ---- 将多行写入 waterfall：向上滚动 n 行，把新块贴到底部 ----
            n = int(gray_block.shape[0])
            if n <= 0:
                return

            if n >= self.wf_height:
                # 块太大：只取最后 wf_height 行
                self.wf[:, :] = gray_block[-self.wf_height:, :]
            else:
                self.wf[:-n, :] = self.wf[n:, :]
                self.wf[-n:, :] = gray_block

            self._render_waterfall()

            self.status.setText(
                f"Status: Running (show=ch{sel_ch}/{sel_kind}, cfg_scan={cfg_scan}, mode={cfg_mode}, pw={pw}, sd={sd}, cb_lines={num_lines}, points={point_count})"
            )

        except Exception as e:
            self.status.setText(f"Status: Render error: {e}")

    def _render_waterfall(self):
        if self.wf is None:
            return

        h, w = self.wf.shape
        img = np.ascontiguousarray(self.wf)

        qimg = QImage(
            img.data,
            w,
            h,
            w,  # bytesPerLine for Grayscale8 is width * 1
            QImage.Format_Grayscale8
        )

        pixmap = QPixmap.fromImage(qimg)
        self.display.setPixmap(
            pixmap.scaled(
                self.display.size(),
                Qt.IgnoreAspectRatio,
                Qt.FastTransformation
            )
        )

    def closeEvent(self, event):
        try:
            self.worker.stop()
        except Exception:
            pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())