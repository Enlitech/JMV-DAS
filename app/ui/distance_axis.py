import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget


class DistanceAxis(QWidget):
    SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
    FIBER_REFRACTIVE_INDEX = 1.468
    ADC_SAMPLE_RATE_HZ = 250_000_000.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._point_count = 0
        self._scale_down = 1
        self._selected_col = 0
        self._view_start_col = 0
        self._view_point_count = 0

        self.setMinimumHeight(56)
        self.setMaximumHeight(56)

    @classmethod
    def base_spacing_m(cls) -> float:
        return cls.SPEED_OF_LIGHT_M_PER_S / (
            2.0 * cls.FIBER_REFRACTIVE_INDEX * cls.ADC_SAMPLE_RATE_HZ
        )

    def spacing_m(self) -> float:
        return self.base_spacing_m() * max(1, int(self._scale_down))

    def max_distance_m(self) -> float:
        if self._point_count <= 1:
            return 0.0
        return (self._point_count - 1) * self.spacing_m()

    def set_axis_state(
        self,
        point_count: int,
        scale_down: int,
        selected_col: int,
        view_start_col: int | None = None,
        view_point_count: int | None = None,
    ):
        point_count = max(0, int(point_count))
        scale_down = max(1, int(scale_down))
        selected_col = max(0, int(selected_col))

        if point_count > 0:
            selected_col = min(selected_col, point_count - 1)
        else:
            selected_col = 0

        if view_start_col is None:
            view_start_col = 0
        if view_point_count is None:
            view_point_count = point_count

        if point_count > 0:
            view_start_col = max(0, min(int(view_start_col), point_count - 1))
            view_point_count = max(1, min(int(view_point_count), point_count - view_start_col))
        else:
            view_start_col = 0
            view_point_count = 0

        state = (point_count, scale_down, selected_col, view_start_col, view_point_count)
        old_state = (
            self._point_count,
            self._scale_down,
            self._selected_col,
            self._view_start_col,
            self._view_point_count,
        )
        if state == old_state:
            return

        self._point_count = point_count
        self._scale_down = scale_down
        self._selected_col = selected_col
        self._view_start_col = view_start_col
        self._view_point_count = view_point_count
        self.setToolTip(
            (
                f"Distance axis: {self.spacing_m():.3f} m/sample, "
                f"view {self._format_distance(self._view_start_col * self.spacing_m())}"
                f" - {self._format_distance(self._view_end_col() * self.spacing_m())}"
            )
            if point_count > 0
            else "Distance axis: waiting for data"
        )
        self.update()

    def _view_end_col(self) -> int:
        if self._view_point_count <= 0:
            return self._view_start_col
        return self._view_start_col + self._view_point_count - 1

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect()
        painter.fillRect(rect, self.palette().window())

        fm = QFontMetrics(self.font())
        left = 12
        right = 12
        top = 8
        axis_y = top + 12
        bottom_text_y = rect.height() - 8

        label = "Distance (m)"
        painter.setPen(QColor("#303030"))
        painter.drawText(left, rect.height() - 28, label)

        x0 = left
        x1 = max(left + 1, rect.width() - right)
        span_px = x1 - x0

        painter.setPen(QPen(QColor("#404040"), 1))
        painter.drawLine(x0, axis_y, x1, axis_y)

        if self._point_count <= 1 or self._view_point_count <= 0 or span_px <= 1:
            painter.setPen(QColor("#707070"))
            painter.drawText(left, bottom_text_y, "Waiting for acquisition data")
            return

        view_start_distance = self._view_start_col * self.spacing_m()
        view_end_distance = self._view_end_col() * self.spacing_m()
        view_span_distance = max(0.0, view_end_distance - view_start_distance)

        target_major_intervals = max(6, min(10, span_px // 120))
        tick_step = self._nice_step(view_span_distance / target_major_intervals) if view_span_distance > 0 else 1.0
        minor_step = tick_step / 2.0

        if minor_step > 0 and view_span_distance > 0:
            painter.setPen(QPen(QColor("#707070"), 1))
            tick = math.ceil(view_start_distance / minor_step) * minor_step
            while tick < view_end_distance:
                x = x0 + int(round(((tick - view_start_distance) / view_span_distance) * span_px))
                painter.drawLine(x, axis_y, x, axis_y + 3)
                tick += minor_step

        tick = math.ceil(view_start_distance / tick_step) * tick_step if tick_step > 0 else view_start_distance
        painter.setPen(QPen(QColor("#404040"), 1))
        while tick <= view_end_distance + tick_step * 0.5:
            x = (
                x0 + int(round(((tick - view_start_distance) / view_span_distance) * span_px))
                if view_span_distance > 0 else x0
            )
            painter.drawLine(x, axis_y, x, axis_y + 6)

            text = self._format_distance(tick)
            text_width = fm.horizontalAdvance(text)
            text_x = max(0, min(rect.width() - text_width, x - text_width // 2))
            painter.drawText(text_x, bottom_text_y, text)
            tick += tick_step

        selected_distance = self._selected_col * self.spacing_m()
        if view_start_distance <= selected_distance <= view_end_distance and view_span_distance > 0:
            selected_x = x0 + int(round(((selected_distance - view_start_distance) / view_span_distance) * span_px))
            painter.setPen(QPen(QColor("#b03030"), 1))
            painter.drawLine(selected_x, axis_y - 6, selected_x, axis_y + 10)
        elif view_span_distance == 0:
            painter.setPen(QPen(QColor("#b03030"), 1))
            painter.drawLine(x0, axis_y - 6, x0, axis_y + 10)

        selected_text = f"col {self._selected_col}: {self._format_distance(selected_distance)}"
        selected_width = fm.horizontalAdvance(selected_text)
        painter.setPen(QColor("#505050"))
        painter.drawText(max(left, rect.width() - right - selected_width), rect.height() - 28, selected_text)

    @staticmethod
    def _nice_step(raw_step: float) -> float:
        if raw_step <= 0:
            return 1.0

        exponent = math.floor(math.log10(raw_step))
        fraction = raw_step / (10 ** exponent)

        if fraction <= 1:
            nice_fraction = 1
        elif fraction <= 2:
            nice_fraction = 2
        elif fraction <= 5:
            nice_fraction = 5
        else:
            nice_fraction = 10

        return nice_fraction * (10 ** exponent)

    @staticmethod
    def _format_distance(value_m: float) -> str:
        if value_m >= 1000.0:
            return f"{value_m / 1000.0:.1f} km"
        if value_m >= 100.0:
            return f"{value_m:.0f} m"
        if value_m >= 10.0:
            return f"{value_m:.1f} m"
        return f"{value_m:.2f} m"
