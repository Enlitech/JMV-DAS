import numpy as np


class WaterfallTransform:
    """
    block(float32) -> gray(uint8)

    Supported modes:
      - "Linear"              : raw percentile scaling
      - "Abs"                 : abs(raw) percentile scaling
      - "Log(dB)"             : 20*log10(abs(raw)+eps) percentile scaling
      - "HP(MeanRemove)"      : raw - row_mean percentile scaling

      - "EnergyLog(MSE)"      : per-position rolling window MSE energy -> log10 -> ABS range scaling
                               (window along time axis, i.e. rows)
    """
    def __init__(self):
        self.mode = "Linear"

        # percentile scaling params (legacy modes)
        self.p_lo = 5.0
        self.p_hi = 95.0

        # shared
        self.gamma = 1.0
        self.invert = True
        self.eps = 1e-6

        # absolute scaling params (for EnergyLog(MSE) or any ABS-range mode you add)
        self.vmin = -6.0   # applied AFTER log10
        self.vmax = 0.0    # applied AFTER log10

        # rolling energy params
        self.energy_win = 32   # window length in "lines"
        self.use_log10 = True  # log10 or natural log

    def apply(self, block: np.ndarray) -> np.ndarray:
        x = np.asarray(block, dtype=np.float32)

        # --- preprocessing / feature extraction ---
        if self.mode == "Abs":
            feat = np.abs(x)
            return self._percentile_to_gray(feat)

        if self.mode == "Log(dB)":
            feat = 20.0 * np.log10(np.abs(x) + float(self.eps))
            return self._percentile_to_gray(feat)

        if self.mode == "HP(MeanRemove)":
            feat = x - np.mean(x, axis=1, keepdims=True)
            return self._percentile_to_gray(feat)

        if self.mode == "EnergyLog(MSE)":
            feat = self._rolling_mse_energy(x, win=self.energy_win)  # >= 0
            if self.use_log10:
                feat = np.log10(feat + float(self.eps))
            else:
                feat = np.log(feat + float(self.eps))
            return self._absrange_to_gray(feat, vmin=self.vmin, vmax=self.vmax)

        # default: Linear
        return self._percentile_to_gray(x)

    # -----------------------------
    # Mode helpers
    # -----------------------------
    def _rolling_mse_energy(self, x: np.ndarray, win: int) -> np.ndarray:
        """
        Rolling window MSE (mean square) along time axis (rows).

        x: (T, P)
        return: (T, P) where each row t is energy over window ending at t:
                mean(x[t-win+1:t+1]^2), with smaller windows for t < win-1.
        """
        x = np.asarray(x, dtype=np.float32)
        T = int(x.shape[0])
        if T <= 0:
            return x

        win = int(win)
        if win <= 1:
            return x * x

        # cumulative sum of squares for O(T*P)
        xsq = x * x
        csum = np.cumsum(xsq, axis=0)  # (T,P)

        out = np.empty_like(xsq)

        # for t < win: use [0..t]
        # energy = csum[t] / (t+1)
        idx0 = min(win - 1, T - 1)
        denom0 = (np.arange(0, idx0 + 1, dtype=np.float32) + 1.0).reshape(-1, 1)
        out[:idx0 + 1] = csum[:idx0 + 1] / denom0

        if T > win:
            # for t >= win-1: use window [t-win+1 .. t]
            # sum = csum[t] - csum[t-win]
            sums = csum[win - 1:] - np.vstack([np.zeros((1, x.shape[1]), dtype=np.float32), csum[:-win]])
            out[win - 1:] = sums / float(win)

        return out

    # -----------------------------
    # Scaling to grayscale
    # -----------------------------
    def _percentile_to_gray(self, feat: np.ndarray) -> np.ndarray:
        """Old behavior: percentile scaling (robust)."""
        x = np.asarray(feat, dtype=np.float32)

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

        return self._post_to_gray(y)

    def _absrange_to_gray(self, feat: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
        """New behavior: absolute scaling with fixed vmin/vmax."""
        x = np.asarray(feat, dtype=np.float32)

        vmin = float(vmin)
        vmax = float(vmax)
        if vmax <= vmin:
            vmax = vmin + 1e-6

        y = (x - vmin) / (vmax - vmin)
        y = np.clip(y, 0.0, 1.0)

        return self._post_to_gray(y)

    def _post_to_gray(self, y01: np.ndarray) -> np.ndarray:
        """Apply gamma + invert + uint8 conversion."""
        y = np.asarray(y01, dtype=np.float32)

        g = float(self.gamma)
        if np.isfinite(g) and g > 0 and abs(g - 1.0) > 1e-6:
            y = np.power(y, g)

        if self.invert:
            gray = ((1.0 - y) * 255.0).astype(np.uint8)
        else:
            gray = (y * 255.0).astype(np.uint8)

        return gray