import numpy as np


class WaterfallTransform:
    """
    block(float32) -> gray(uint8)

    Supported modes:
      - "Linear"
      - "Abs"
      - "Log(dB)"
      - "HP(MeanRemove)"
    """
    def __init__(self):
        self.mode = "Linear"
        self.p_lo = 5.0
        self.p_hi = 95.0
        self.gamma = 1.0
        self.invert = True
        self.eps = 1e-6

    def apply(self, block: np.ndarray) -> np.ndarray:
        x = np.asarray(block, dtype=np.float32)

        # --- preprocessing ---
        if self.mode == "Abs":
            x = np.abs(x)
        elif self.mode == "Log(dB)":
            x = 20.0 * np.log10(np.abs(x) + float(self.eps))
        elif self.mode == "HP(MeanRemove)":
            x = x - np.mean(x, axis=1, keepdims=True)
        else:
            pass  # Linear

        # --- robust scaling ---
        p_lo = float(self.p_lo)
        p_hi = float(self.p_hi)
        if p_hi <= p_lo:
            p_hi = p_lo + 1e-3

        lo = np.percentile(x, p_lo)
        hi = np.percentile(x, p_hi)

        if not np.isfinite(lo) or not np.isfinite(hi) or (hi - lo) < 1e-12:
            lo = float(np.nanmin(x))
            hi = float(np.nanmax(x)) + 1e-6

        y = (x - lo) / (hi - lo)
        y = np.clip(y, 0.0, 1.0)

        # --- gamma ---
        g = float(self.gamma)
        if np.isfinite(g) and g > 0 and abs(g - 1.0) > 1e-6:
            y = np.power(y, g)

        # --- invert + to uint8 ---
        if self.invert:
            gray = ((1.0 - y) * 255.0).astype(np.uint8)
        else:
            gray = (y * 255.0).astype(np.uint8)

        return gray