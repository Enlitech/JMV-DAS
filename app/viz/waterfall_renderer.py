import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel


class WaterfallRenderer:
    def __init__(self, wf_height: int = 600):
        self.wf_height = int(wf_height)
        self.wf_width = None
        self.wf = None  # uint8[H,W] grayscale

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

    # -----------------------------
    # Heatmap colormap
    # -----------------------------
    def _colormap_blue_orange_red(self, gray: np.ndarray) -> np.ndarray:
        """
        gray: uint8[H,W] in [0,255]
        return: uint8[H,W,3] RGB
        """

        x = gray.astype(np.float32) / 255.0  # normalize 0~1

        # Allocate RGB
        h, w = x.shape
        rgb = np.zeros((h, w, 3), dtype=np.float32)

        # Define anchor colors
        c0 = np.array([0, 0, 80], dtype=np.float32)      # dark blue
        c1 = np.array([255, 140, 0], dtype=np.float32)   # orange
        c2 = np.array([255, 0, 0], dtype=np.float32)     # red

        # Split at 0.5
        mask = x <= 0.5

        # Blue → Orange
        t0 = (x / 0.5)
        rgb[mask] = (
            c0 + (c1 - c0) * t0[mask][..., None]
        )

        # Orange → Red
        t1 = (x - 0.5) / 0.5
        rgb[~mask] = (
            c1 + (c2 - c1) * t1[~mask][..., None]
        )

        return np.clip(rgb, 0, 255).astype(np.uint8)

    # -----------------------------
    # Render
    # -----------------------------
    def render_to_label(self, label: QLabel):
        if self.wf is None:
            return

        # Apply colormap
        rgb_img = self._colormap_blue_orange_red(self.wf)

        h, w, _ = rgb_img.shape
        img = np.ascontiguousarray(rgb_img)

        qimg = QImage(
            img.data,
            w,
            h,
            3 * w,
            QImage.Format_RGB888
        )

        pixmap = QPixmap.fromImage(qimg)

        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.IgnoreAspectRatio,
                Qt.FastTransformation
            )
        )