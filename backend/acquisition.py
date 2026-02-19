import threading
import queue
import numpy as np
from PySide6.QtCore import QObject, Signal

from backend.pyexplorex import PyExploreX


class AcquisitionWorker(QObject):
    # payload: (scan_rate:int, point_count:int, arr:np.ndarray[float32])
    data_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.handler = PyExploreX()
        self.queue = queue.Queue(maxsize=50)
        self.running = False
        self._consumer_thread = None

    def start(self):
        if self.running:
            return

        self.handler.create()
        self.handler.setParams(scaleDown=3)
        self.handler.setBlockCount()

        self.handler.setAmpDataCallback(self._amp_callback)

        if self.handler.open() != 0:
            print("Failed to open device")
            return

        if self.handler.start() != 0:
            print("Failed to start device")
            return

        self.running = True
        self._consumer_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._consumer_thread.start()

    def stop(self):
        if not self.running:
            return
        self.running = False

        try:
            self.handler.stop()
        except Exception:
            pass

        try:
            self.handler.destroy()
        except Exception:
            pass

        # 清空队列
        try:
            while True:
                self.queue.get_nowait()
        except queue.Empty:
            pass

    def _amp_callback(self, scan_rate, point_count, data_ptr, size):
        """
        data 是 float32 buffer（来自 vendor cpp 示例）
        """
        try:
            raw = bytes(data_ptr[:size])

            # float32
            arr = np.frombuffer(raw, dtype=np.float32)

            payload = (int(scan_rate), int(point_count), arr)

            # queue 满了丢旧的（演示软件优先最新画面）
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    pass
            self.queue.put_nowait(payload)
        except Exception as e:
            print(f"_amp_callback error: {e}")

    def _process_loop(self):
        while self.running:
            try:
                payload = self.queue.get(timeout=1)
                self.data_ready.emit(payload)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"_process_loop error: {e}")
