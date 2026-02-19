import threading
import queue
import numpy as np
from PySide6.QtCore import QObject, Signal

from backend.pyexplorex import PyExploreX


class AcquisitionWorker(QObject):
    # payload:
    # (scan_rate:int, point_count:int, num_lines:int, block2d: np.ndarray[float32] shape=(num_lines, point_count))
    data_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.handler = PyExploreX()
        self.queue = queue.Queue(maxsize=10)  # 多行 block 大，队列别太大
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
        C callback buffer is float32 list, and typically contains multiple lines:
        total_floats = size / 4
        num_lines = total_floats / point_count
        """
        try:
            scan_rate = int(scan_rate)
            point_count = int(point_count)
            if point_count <= 0 or size <= 0:
                return

            raw = bytes(data_ptr[:size])
            arr = np.frombuffer(raw, dtype=np.float32)

            total = int(arr.size)
            num_lines = total // point_count
            if num_lines <= 0:
                return

            # 丢掉尾部不完整部分（如果有）
            total2 = num_lines * point_count
            if total2 != total:
                arr = arr[:total2]

            block2d = arr.reshape((num_lines, point_count))

            payload = (scan_rate, point_count, num_lines, block2d)

            # queue 满了就丢旧块（保持“最新画面”）
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
