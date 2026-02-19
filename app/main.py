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

        self.setWindowTitle("JMV-DAS Demo")
        self.resize(1100, 700)

        # -------------------------
        # UI Layout
        # -------------------------
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout()
        central.setLayout(main_layout)

        # Left control panel
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
        self.scale_down.setValue(3)

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

        control_layout.addSpacing(16)
        control_layout.addWidget(self.btn_open)
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)

        control_layout.addSpacing(16)
        control_layout.addWidget(self.status)
        control_layout.addStretch()

        # Right display (waterfall)
        self.display = QLabel("Waterfall Display")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setStyleSheet("background-color: black; color: white;")
        self.display.setMinimumSize(800, 600)

        main_layout.addLayout(control_layout, 0)
        main_layout.addWidget(self.display, 1)

        # -------------------------
        # Worker
        # -------------------------
        self.worker = AcquisitionWorker()
        self.worker.data_ready.connect(self.on_data_ready)

        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_open.clicked.connect(self.on_open_clicked)

        # -------------------------
        # Waterfall buffer (dynamic)
        # -------------------------
        self.wf_width = None
        self.wf_height = 600
        self.wf = None  # np.uint8[H,W]

        # 控制 UI 刷新频率：用 timer 统一刷新更稳
        self._latest_payload = None
        self._last_update_ts = 0.0
        self._min_ui_interval = 1.0 / 30.0  # 30 FPS

        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / 30))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -------------------------
    # UI handlers
    # -------------------------
    def on_open_clicked(self):
        self.status.setText("Status: Open is noop (Start will open).")

    def on_start_clicked(self):
        try:
            self.status.setText("Status: Starting...")
            self.worker.start()
            self.status.setText("Status: Running")
        except Exception as e:
            self.status.setText(f"Status: Start failed: {e}")

    def on_stop_clicked(self):
        try:
            self.worker.stop()
            self.status.setText("Status: Stopped")
        except Exception as e:
            self.status.setText(f"Status: Stop failed: {e}")

    # -------------------------
    # Data path
    # -------------------------
    def on_data_ready(self, payload: object):
        """
        payload: (scan_rate:int, point_count:int, arr:np.ndarray)
        """
        self._latest_payload = payload

    def _ensure_waterfall(self, width: int):
        if self.wf_width == width and self.wf is not None:
            return

        self.wf_width = int(width)
        self.wf = np.zeros((self.wf_height, self.wf_width), dtype=np.uint8)
        self.status.setText(f"Status: Waterfall resized to {self.wf_width}x{self.wf_height}")

    def _tick(self):
        if self._latest_payload is None:
            return

        now = time.time()
        if now - self._last_update_ts < self._min_ui_interval:
            return
        self._last_update_ts = now

        payload = self._latest_payload
        self._latest_payload = None

        try:
            scan_rate, point_count, arr = payload
            if not isinstance(arr, np.ndarray):
                return
            if arr.ndim != 1:
                arr = arr.ravel()

            # 动态适配宽度
            width = int(point_count) if int(point_count) > 0 else arr.size
            if width <= 0:
                return

            self._ensure_waterfall(width)

            # 取一行数据：尽量使用 arr 前 width 个点
            if arr.size >= width:
                line = arr[:width]
            else:
                pad = np.zeros((width - arr.size,), dtype=arr.dtype)
                line = np.concatenate([arr, pad], axis=0)

            # ---- 映射到 0..255 灰度（robust scaling）----
            x = line.astype(np.float32)

            lo = np.percentile(x, 5)
            hi = np.percentile(x, 95)
            if hi - lo < 1e-6:
                lo = float(np.min(x))
                hi = float(np.max(x)) + 1e-6

            x = (x - lo) / (hi - lo)
            x = np.clip(x, 0.0, 1.0)

            # 若你希望“背景更亮、事件更暗”，可以反相：
            # gray = ((1.0 - x) * 255.0).astype(np.uint8)
            gray = (x * 255.0).astype(np.uint8)

            # ---- 滚动 ----
            self.wf[:-1, :] = self.wf[1:, :]
            self.wf[-1, :] = gray

            self._render_waterfall()
            self.status.setText(f"Status: Running (scan_rate={scan_rate}, point_count={point_count}, arr={arr.size})")

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
            w,  # bytesPerLine
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
