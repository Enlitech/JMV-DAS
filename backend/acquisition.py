import time
import threading
import queue
import numpy as np
from PySide6.QtCore import QObject, Signal

from backend.pyexplorex import PyExploreX, Aom, ScanRate, Mode

class AcquisitionWorker(QObject):
    data_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.handler = PyExploreX()
        self.queue = queue.Queue(maxsize=6)
        self.running = False
        self._consumer_thread = None

        self.cfg_scan_rate_label = "10k"
        self.cfg_mode_label = "Coherent Suppression"
        self.cfg_pulse_width = 100
        self.cfg_scale_down = 5

        # IMPORTANT: keep callback refs alive
        self._cb_refs = []

    # ... _map_scan_rate/_map_mode unchanged ...

    def start(self, scan_rate_label: str, mode_label: str, pulse_width: int, scale_down: int):
        if self.running:
            return

        self.cfg_scan_rate_label = scan_rate_label
        self.cfg_mode_label = mode_label
        self.cfg_pulse_width = int(pulse_width)
        self.cfg_scale_down = int(scale_down)

        scan_rate_enum = self._map_scan_rate(scan_rate_label)
        mode_enum = self._map_mode(mode_label)

        self.handler.create()
        self.handler.setParams(
            aom=Aom.Aom80,
            scanRate=scan_rate_enum,
            mode=mode_enum,
            pulseWidth=self.cfg_pulse_width,
            scaleDown=self.cfg_scale_down
        )
        self.handler.setBlockCount()

        # ---- register 4 callbacks ----
        self._cb_refs.clear()
        cb_amp_ch1   = self._make_cb(ch=1, kind="amp")
        cb_phase_ch1 = self._make_cb(ch=1, kind="phase")
        cb_amp_ch2   = self._make_cb(ch=2, kind="amp")
        cb_phase_ch2 = self._make_cb(ch=2, kind="phase")
        self._cb_refs.extend([cb_amp_ch1, cb_phase_ch1, cb_amp_ch2, cb_phase_ch2])

        self.handler.setAmpDataCallback(cb_amp_ch1)
        self.handler.setPhaseDataCallback(cb_phase_ch1)
        self.handler.setAmpDataCallbackCh2(cb_amp_ch2)
        self.handler.setPhaseDataCallbackCh2(cb_phase_ch2)

        if self.handler.open() != 0:
            try: self.handler.destroy()
            except Exception: pass
            return

        if self.handler.start() != 0:
            try: self.handler.destroy()
            except Exception: pass
            return

        self.running = True
        self._consumer_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._consumer_thread.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        try: self.handler.stop()
        except Exception: pass
        try: self.handler.destroy()
        except Exception: pass

        try:
            while True:
                self.queue.get_nowait()
        except queue.Empty:
            pass

        self._cb_refs.clear()

    def _make_cb(self, ch: int, kind: str):
        # Returns a Python callable with signature (scan_rate, point_count, data_ptr, size)
        def _cb(scan_rate, point_count, data_ptr, size):
            self._on_block(ch=ch, kind=kind,
                           scan_rate=scan_rate,
                           point_count=point_count,
                           data_ptr=data_ptr,
                           size=size)
        return _cb

    def _on_block(self, ch: int, kind: str, scan_rate, point_count, data_ptr, size):
        """
        kind in {"amp","phase"}
        ch in {1,2}
        """
        try:
            cb_lines = int(scan_rate)  # vendor sample: first arg used as "lines"
            point_count = int(point_count)
            size = int(size)

            if point_count <= 0 or size <= 0:
                return

            raw = bytes(data_ptr[:size])
            arr = np.frombuffer(raw, dtype=np.float32)

            total = int(arr.size)
            if cb_lines > 0 and cb_lines * point_count <= total:
                num_lines = cb_lines
            else:
                num_lines = total // point_count

            if num_lines <= 0:
                return

            total2 = num_lines * point_count
            if total2 != total:
                arr = arr[:total2]

            block2d = arr.reshape((num_lines, point_count))

            payload = {
                "cfg_scan_rate": self.cfg_scan_rate_label,
                "cfg_mode": self.cfg_mode_label,
                "cfg_pulse_width": self.cfg_pulse_width,
                "cfg_scale_down": self.cfg_scale_down,
                "channel": int(ch),
                "kind": str(kind),             # "amp" or "phase"
                "cb_lines": int(num_lines),
                "point_count": int(point_count),
                "block": block2d,
                "ts": time.time(),
            }

            if self.queue.full():
                try: self.queue.get_nowait()
                except queue.Empty: pass
            self.queue.put_nowait(payload)

        except Exception as e:
            print(f"_on_block error (ch={ch}, kind={kind}): {e}")

    def _process_loop(self):
        while self.running:
            try:
                payload = self.queue.get(timeout=1)
                self.data_ready.emit(payload)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"_process_loop error: {e}")