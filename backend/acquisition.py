import threading
import queue
import numpy as np
from PySide6.QtCore import QObject, Signal

from backend.explorex import PyExploreX


class AcquisitionWorker(QObject):
    data_ready = Signal(object)  # 发 numpy 数组给 UI

    def __init__(self):
        super().__init__()
        self.handler = PyExploreX()
        self.queue = queue.Queue()
        self.running = False

    def start(self):
        self.handler.create()
        self.handler.setParams(scaleDown=3)
        self.handler.setBlockCount()

        # 注册回调
        self.handler.setAmpDataCallback(self._amp_callback)

        if self.handler.open() != 0:
            print("Failed to open device")
            return

        self.handler.start()
        self.running = True

        # 启动消费线程
        threading.Thread(target=self._process_loop, daemon=True).start()

    def stop(self):
        self.running = False
        self.handler.stop()
        self.handler.destroy()

    def _amp_callback(self, scan_rate, point_count, data_ptr, size):
        raw = bytes(data_ptr[:size])
        arr = np.frombuffer(raw, dtype=np.int16)  # 根据实际数据类型改
        self.queue.put(arr)

    def _process_loop(self):
        while self.running:
            try:
                data = self.queue.get(timeout=1)
                self.data_ready.emit(data)
            except queue.Empty:
                continue
