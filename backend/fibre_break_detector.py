from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FibreBreakResult:
    fibre_name: str
    first_high_pos: int
    first_high_distance_m: float
    healthy: bool
    abnormal: bool
    threshold: float
    min_length_m: float


class FibreBreakDetector:
    SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
    FIBER_REFRACTIVE_INDEX = 1.468
    ADC_SAMPLE_RATE_HZ = 250_000_000.0

    def __init__(self, spatial_ewma_alpha: float = 0.2, threshold: float = 1000.0, min_length_m: float = 100.0):
        self.spatial_ewma_alpha = float(spatial_ewma_alpha)
        self.threshold = float(threshold)
        self.min_length_m = float(min_length_m)
        self._emv_profiles: dict[str, np.ndarray] = {}

    @classmethod
    def base_spacing_m(cls) -> float:
        return cls.SPEED_OF_LIGHT_M_PER_S / (
            2.0 * cls.FIBER_REFRACTIVE_INDEX * cls.ADC_SAMPLE_RATE_HZ
        )

    def configure(self, spatial_ewma_alpha: float, threshold: float, min_length_m: float):
        self.spatial_ewma_alpha = float(spatial_ewma_alpha)
        self.threshold = float(threshold)
        self.min_length_m = float(min_length_m)

    def reset(self):
        self._emv_profiles = {}

    def update(self, block: np.ndarray, scale_down: int, fibre_name: str = "main") -> FibreBreakResult:
        fibre_key = self._normalize_fibre_name(fibre_name)
        raw_block = np.asarray(block, dtype=np.float32)
        if raw_block.ndim != 2 or raw_block.size == 0:
            return FibreBreakResult(
                fibre_name=fibre_key,
                first_high_pos=-1,
                first_high_distance_m=-1.0,
                healthy=False,
                abnormal=True,
                threshold=float(self.threshold),
                min_length_m=float(self.min_length_m),
            )

        profile = np.mean(raw_block, axis=0, dtype=np.float32)
        profile = np.asarray(profile, dtype=np.float32).reshape(-1)
        emv_profile = self._update_emv(profile, fibre_key)

        first_high_pos = self._find_first_high_from_end(emv_profile, self.threshold)
        if first_high_pos >= 0:
            distance_m = float(first_high_pos) * self.base_spacing_m() * max(1, int(scale_down))
        else:
            distance_m = -1.0

        healthy = distance_m >= float(self.min_length_m)
        return FibreBreakResult(
            fibre_name=fibre_key,
            first_high_pos=int(first_high_pos),
            first_high_distance_m=float(distance_m),
            healthy=bool(healthy),
            abnormal=not bool(healthy),
            threshold=float(self.threshold),
            min_length_m=float(self.min_length_m),
        )

    @staticmethod
    def _normalize_fibre_name(fibre_name: str) -> str:
        name = (fibre_name or "").strip().lower()
        return "standby" if name == "standby" else "main"

    def _update_emv(self, src: np.ndarray, fibre_name: str) -> np.ndarray:
        src = np.asarray(src, dtype=np.float32).reshape(-1)
        emv = self._emv_profiles.get(fibre_name)
        if emv is None or src.size != emv.size:
            emv = src.copy()
            self._emv_profiles[fibre_name] = emv
            return emv

        if src.size == 0:
            return emv

        alpha = min(max(float(self.spatial_ewma_alpha), 0.0), 1.0)
        emv[0] = src[0]
        for idx in range(1, src.size):
            emv[idx] = alpha * src[idx] + (1.0 - alpha) * emv[idx - 1]
        return emv

    @staticmethod
    def _find_first_high_from_end(values: np.ndarray, threshold: float) -> int:
        for idx in range(int(values.size) - 1, -1, -1):
            if float(values[idx]) > float(threshold):
                return idx
        return -1
