import threading
import queue
import numpy as np
from PySide6.QtCore import QObject, Signal

from backend.pyexplorex import PyExploreX


class AcquisitionWorker(QObject):
    # payload: (scan_rate:int, point_count:int, arr:np.ndarray)
    data_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.handler = PyExploreX()
        self.queue = queue.Queue(maxsize=50)  # 防止生产过快撑爆内存
        self.running = False
        self._consumer_thread = None

    def start(self):
        if self.running:
            return

        self.handler.create()
        self.handler.setParams(scaleDown=3)
        self.handler.setBlockCount()

        # 注册回调（这里只接 amp ch1，你可后续加 phase/ch2）
        self.handler.setAmpDataCallback(self._amp_callback)

        if self.handler.open() != 0:
            print("Failed to open device")
            return

        if self.handler.start() != 0:
            print("Failed to start device")
            return

        self.running = True

        # 启动消费线程
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

        # 尽量清空队列，避免退出时堆积
        try:
            while True:
                self.queue.get_nowait()
        except queue.Empty:
            pass

    def _amp_callback(self, scan_rate, point_count, data_ptr, size):
        """
        C 回调线程：只做极轻的工作 -> bytes->np，然后丢进 queue。
        """
        try:
            # data_ptr: POINTER(c_char)
            raw = bytes(data_ptr[:size])

            # !!! dtype 需要按你的真实数据格式调整 !!!
            arr = np.frombuffer(raw, dtype=np.int16)

            payload = (int(scan_rate), int(point_count), arr)

            # queue 满了就丢掉旧数据（演示软件更重要的是“最新画面”）
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    pass
            self.queue.put_nowait(payload)
        except Exception as e:
            print(f"_amp_callback error: {e}")

    def _process_loop(self):
        """
        Python 线程：从 queue 拿数据，通过 Qt signal 发送到 UI 线程。
        """
        while self.running:
            try:
                payload = self.queue.get(timeout=1)
                self.data_ready.emit(payload)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"_process_loop error: {e}")
