import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel


class WaterfallRenderer:
    def __init__(self, wf_height: int = 600):
        self.wf_height = int(wf_height)
        self.wf_width = None
        self.wf = None  # uint8[H,W]

    def ensure(self, width: int):
        width = int(width)
        if width <= 0:
            return
        if self.wf is not None and self.wf_width == width:
            return
        self.wf_width = width
        self.wf = np.zeros((self.wf_height, self.wf_width), dtype=np.uint8)

    def push_block(self, gray_block: np.ndarray):
        if self.wf is None:
            return
        gray_block = np.asarray(gray_block, dtype=np.uint8)
        if gray_block.ndim != 2 or gray_block.shape[1] != self.wf_width:
            return

        n = int(gray_block.shape[0])
        if n <= 0:
            return

        if n >= self.wf_height:
            self.wf[:, :] = gray_block[-self.wf_height:, :]
        else:
            self.wf[:-n, :] = self.wf[n:, :]
            self.wf[-n:, :] = gray_block

    def render_to_label(self, label: QLabel):
        if self.wf is None:
            return

        h, w = self.wf.shape
        img = np.ascontiguousarray(self.wf)

        qimg = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(qimg)

        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.IgnoreAspectRatio,
                Qt.FastTransformation
            )
        )