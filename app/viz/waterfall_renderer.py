import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel


class WaterfallRenderer:
    def __init__(self, wf_height: int = 600):
        self.wf_height = int(wf_height)
        self.wf_width = None
        self.wf = None  # uint8[H,W] grayscale
        self.values = None  # float32[H,W] raw value buffer aligned with wf rows
        self.row_times = None  # float64[H] wall-clock time per row
        self._lines_per_row = 1
        self._pending_count = 0
        self._pending_gray_sum = None
        self._pending_raw_sum = None
        self._pending_raw_count = 0
        self._pending_time_sum = 0.0
        self._pending_time_count = 0

    def clear(self):
        if self.wf is not None:
            self.wf.fill(0)
        if self.values is not None:
            self.values.fill(np.nan)
        if self.row_times is not None:
            self.row_times.fill(np.nan)
        self._reset_pending()

    @property
    def lines_per_row(self) -> int:
        return int(self._lines_per_row)

    def set_lines_per_row(self, lines_per_row: int) -> bool:
        new_value = max(1, int(lines_per_row))
        if new_value == self._lines_per_row:
            return False
        self._lines_per_row = new_value
        self.clear()
        return True

    def _reset_pending(self):
        self._pending_count = 0
        self._pending_raw_count = 0
        self._pending_time_sum = 0.0
        self._pending_time_count = 0
        if self.wf_width is not None and self.wf_width > 0:
            self._pending_gray_sum = np.zeros(self.wf_width, dtype=np.float32)
            self._pending_raw_sum = np.zeros(self.wf_width, dtype=np.float32)
        else:
            self._pending_gray_sum = None
            self._pending_raw_sum = None

    def ensure(self, width: int):
        width = int(width)
        if width <= 0:
            return
        if self.wf is not None and self.wf_width == width:
            return
        self.wf_width = width
        self.wf = np.zeros((self.wf_height, self.wf_width), dtype=np.uint8)
        self.values = np.full((self.wf_height, self.wf_width), np.nan, dtype=np.float32)
        self.row_times = np.full(self.wf_height, np.nan, dtype=np.float64)
        self._reset_pending()

    def _append_rows(
        self,
        gray_rows: np.ndarray,
        raw_rows: np.ndarray | None = None,
        time_rows: np.ndarray | None = None,
    ):
        rows = np.asarray(gray_rows, dtype=np.uint8)
        if rows.ndim != 2 or rows.shape[1] != self.wf_width:
            return

        n = int(rows.shape[0])
        if n <= 0:
            return

        raw = None
        if raw_rows is not None:
            raw = np.asarray(raw_rows, dtype=np.float32)
            if raw.shape != rows.shape:
                raw = None

        times = None
        if time_rows is not None:
            times = np.asarray(time_rows, dtype=np.float64).reshape(-1)
            if times.size != n:
                times = None

        if n >= self.wf_height:
            self.wf[:, :] = rows[-self.wf_height:, :]
            if self.values is not None:
                if raw is not None:
                    self.values[:, :] = raw[-self.wf_height:, :]
                else:
                    self.values.fill(np.nan)
            if self.row_times is not None:
                if times is not None:
                    self.row_times[:] = times[-self.wf_height:]
                else:
                    self.row_times.fill(np.nan)
            return

        self.wf[:-n, :] = self.wf[n:, :]
        self.wf[-n:, :] = rows
        if self.values is not None:
            self.values[:-n, :] = self.values[n:, :]
            if raw is not None:
                self.values[-n:, :] = raw
            else:
                self.values[-n:, :].fill(np.nan)
        if self.row_times is not None:
            self.row_times[:-n] = self.row_times[n:]
            if times is not None:
                self.row_times[-n:] = times
            else:
                self.row_times[-n:].fill(np.nan)

    def push_block(
        self,
        gray_block: np.ndarray,
        raw_block: np.ndarray | None = None,
        line_times: np.ndarray | None = None,
    ):
        if self.wf is None:
            return

        gray_block = np.asarray(gray_block, dtype=np.uint8)
        if gray_block.ndim != 2 or gray_block.shape[1] != self.wf_width:
            return

        n = int(gray_block.shape[0])
        if n <= 0:
            return

        raw = None
        if raw_block is not None:
            raw = np.asarray(raw_block, dtype=np.float32)
            if raw.shape != gray_block.shape:
                raw = None

        times = None
        if line_times is not None:
            times = np.asarray(line_times, dtype=np.float64).reshape(-1)
            if times.size != n:
                times = None

        if self._lines_per_row <= 1:
            self._append_rows(gray_block, raw_rows=raw, time_rows=times)
            return

        if self._pending_gray_sum is None or self._pending_gray_sum.size != self.wf_width:
            self._reset_pending()

        for i in range(n):
            self._pending_gray_sum += gray_block[i].astype(np.float32, copy=False)
            self._pending_count += 1

            if raw is not None:
                self._pending_raw_sum += raw[i]
                self._pending_raw_count += 1

            if times is not None:
                self._pending_time_sum += float(times[i])
                self._pending_time_count += 1

            if self._pending_count < self._lines_per_row:
                continue

            gray_row = np.rint(self._pending_gray_sum / float(self._pending_count)).astype(np.uint8, copy=False)[None, :]
            raw_row = None
            if self._pending_raw_count > 0:
                raw_row = (self._pending_raw_sum / float(self._pending_raw_count)).astype(np.float32, copy=False)[None, :]
            time_row = None
            if self._pending_time_count > 0:
                time_row = np.array(
                    [self._pending_time_sum / float(self._pending_time_count)],
                    dtype=np.float64,
                )

            self._append_rows(gray_row, raw_rows=raw_row, time_rows=time_row)
            self._reset_pending()

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
    def render_to_label(self, label: QLabel, start_col: int = 0, col_count: int | None = None):
        if self.wf is None:
            return

        total_cols = int(self.wf_width or 0)
        if total_cols <= 0:
            return

        start_col = max(0, min(int(start_col), total_cols - 1))
        if col_count is None:
            col_count = total_cols
        col_count = max(1, min(int(col_count), total_cols - start_col))
        gray_view = self.wf[:, start_col:start_col + col_count]

        # Apply colormap
        rgb_img = self._colormap_blue_orange_red(gray_view)

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
