from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

import numpy as np


class WaterfallRecordingService:
    def __init__(self, root: Path | None = None, queue_size: int = 128):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[2] / "recordings"
        self.queue_size = max(8, int(queue_size))
        self._queue: queue.Queue[tuple[str, dict] | None] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._recording = False
        self._mode = "selected"
        self._session_dir: Path | None = None
        self._chunks_dir: Path | None = None
        self._snapshots_dir: Path | None = None
        self._started_at = 0.0
        self._block_seq = 0
        self._written_blocks = 0
        self._written_bytes = 0
        self._dropped_blocks = 0
        self._last_error = ""
        self._last_snapshot = ""
        self._selected_stream_filter: tuple[int, str] | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return bool(self._recording)

    @property
    def output_root(self) -> Path:
        with self._lock:
            return self.root

    def set_output_root(self, root: str | Path):
        with self._lock:
            self.root = Path(root).expanduser()

    def session_dir(self) -> Path | None:
        with self._lock:
            return self._session_dir

    def start_recording(self, mode: str, metadata: dict | None = None) -> Path:
        selected_mode = "all" if str(mode).strip().lower() == "all" else "selected"
        with self._lock:
            if self._recording:
                raise RuntimeError("Recording is already active.")

            now = time.time()
            session_name = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
            session_dir = self.root.expanduser() / session_name
            chunks_dir = session_dir / "chunks"
            snapshots_dir = session_dir / "snapshots"
            chunks_dir.mkdir(parents=True, exist_ok=False)
            snapshots_dir.mkdir(parents=True, exist_ok=True)

            session_meta = {
                "kind": "waterfall_recording_session",
                "started_at_epoch_s": now,
                "started_at_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                "recording_mode": selected_mode,
                "metadata": metadata or {},
            }
            self._write_json(session_dir / "session.json", session_meta)

            self._queue = queue.Queue(maxsize=self.queue_size)
            self._thread = threading.Thread(
                target=self._writer_loop,
                args=(session_dir, self._queue),
                name="waterfall-recorder",
                daemon=True,
            )
            self._recording = True
            self._mode = selected_mode
            self._session_dir = session_dir
            self._chunks_dir = chunks_dir
            self._snapshots_dir = snapshots_dir
            self._started_at = now
            self._block_seq = 0
            self._written_blocks = 0
            self._written_bytes = 0
            self._dropped_blocks = 0
            self._last_error = ""
            self._last_snapshot = ""
            selected_stream = (metadata or {}).get("selected_stream", {})
            self._selected_stream_filter = (
                int(selected_stream.get("channel", 1)),
                str(selected_stream.get("kind", "phase")),
            )
            self._thread.start()
            return session_dir

    def stop_recording(self):
        with self._lock:
            queue_obj = self._queue
            thread = self._thread
            session_dir = self._session_dir
            was_recording = self._recording
            self._recording = False

        if not was_recording:
            return

        if queue_obj is not None:
            self._enqueue_control(queue_obj, None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

        with self._lock:
            self._queue = None
            self._thread = None
            self._selected_stream_filter = None

        if session_dir is not None:
            summary = self.session_summary()
            summary["stopped_at_epoch_s"] = time.time()
            summary["stopped_at_local"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(summary["stopped_at_epoch_s"]))
            self._write_json(session_dir / "summary.json", summary)

    def handle_payload(self, payload: dict, selected_stream: tuple[int, str]):
        with self._lock:
            if not self._recording or self._queue is None:
                return
            mode = self._mode
            queue_obj = self._queue
            chunks_dir = self._chunks_dir
            selected_filter = self._selected_stream_filter
            seq = self._block_seq + 1
            self._block_seq = seq

        channel = int(payload.get("channel", 1))
        kind = str(payload.get("kind", "phase"))
        if mode == "selected":
            sel_ch, sel_kind = selected_filter or selected_stream
            if channel != int(sel_ch) or kind != str(sel_kind):
                return

        block = np.asarray(payload.get("block"), dtype=np.float32)
        if block.ndim != 2 or block.size == 0 or chunks_dir is None:
            return

        item = {
            "seq": seq,
            "channel": channel,
            "kind": kind,
            "ts": float(payload.get("ts", time.time())),
            "cfg_scan_rate": payload.get("cfg_scan_rate", ""),
            "cfg_mode": payload.get("cfg_mode", ""),
            "cfg_pulse_width": int(payload.get("cfg_pulse_width", 0) or 0),
            "cfg_scale_down": int(payload.get("cfg_scale_down", 0) or 0),
            "cb_lines": int(payload.get("cb_lines", block.shape[0]) or block.shape[0]),
            "point_count": int(payload.get("point_count", block.shape[1]) or block.shape[1]),
            "block": np.array(block, dtype=np.float32, copy=True),
            "chunks_dir": str(chunks_dir),
        }

        try:
            queue_obj.put_nowait(("payload", item))
        except queue.Full:
            try:
                queue_obj.get_nowait()
            except queue.Empty:
                pass
            try:
                queue_obj.put_nowait(("payload", item))
            except queue.Full:
                pass
            with self._lock:
                self._dropped_blocks += 1

    def save_snapshot(
        self,
        pixmap,
        values: np.ndarray | None,
        row_times: np.ndarray | None,
        metadata: dict,
    ) -> Path:
        base_dir = self.session_dir()
        if base_dir is None:
            base_dir = self.root.expanduser() / "snapshots_only"
        snapshots_dir = base_dir / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        stem = f"snapshot_{stamp}"
        png_path = snapshots_dir / f"{stem}.png"
        values_path = snapshots_dir / f"{stem}_values.npy"
        row_times_path = snapshots_dir / f"{stem}_row_times.npy"
        meta_path = snapshots_dir / f"{stem}_meta.json"

        if pixmap is None or pixmap.isNull():
            raise RuntimeError("No rendered waterfall image is available.")
        if not pixmap.save(str(png_path)):
            raise RuntimeError(f"Failed to save snapshot image: {png_path}")

        if values is not None:
            np.save(values_path, np.asarray(values, dtype=np.float32))
        if row_times is not None:
            np.save(row_times_path, np.asarray(row_times, dtype=np.float64))

        self._write_json(meta_path, metadata)
        with self._lock:
            self._last_snapshot = str(png_path)
        return png_path

    def status_text(self) -> str:
        with self._lock:
            if self._recording:
                elapsed = max(0.0, time.time() - self._started_at)
                session_dir = str(self._session_dir) if self._session_dir is not None else "n/a"
                selected_filter = self._selected_stream_filter
                filter_text = ""
                if self._mode == "selected" and selected_filter is not None:
                    filter_text = f", stream=ch{selected_filter[0]}/{selected_filter[1]}"
                return (
                    f"Recording: ON, mode={self._mode}{filter_text}, blocks={self._written_blocks}, "
                    f"dropped={self._dropped_blocks}, size={self._format_bytes(self._written_bytes)}, "
                    f"elapsed={elapsed:.1f}s, dir={session_dir}"
                )
            if self._last_error:
                return f"Recording: ERROR, {self._last_error}"
            if self._last_snapshot:
                return f"Recording: Idle, last snapshot={self._last_snapshot}"
            return "Recording: Idle"

    def session_summary(self) -> dict:
        with self._lock:
            return {
                "recording_mode": self._mode,
                "session_dir": str(self._session_dir) if self._session_dir is not None else "",
                "written_blocks": int(self._written_blocks),
                "written_bytes": int(self._written_bytes),
                "dropped_blocks": int(self._dropped_blocks),
                "last_error": self._last_error,
                "last_snapshot": self._last_snapshot,
            }

    def _writer_loop(self, session_dir: Path, queue_obj: queue.Queue):
        try:
            index_path = session_dir / "chunks" / "index.jsonl"
            while True:
                item = queue_obj.get()
                if item is None:
                    break
                item_kind, data = item
                if item_kind != "payload":
                    continue
                self._write_payload(data, index_path)
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)

    def _write_payload(self, data: dict, index_path: Path):
        seq = int(data["seq"])
        channel = int(data["channel"])
        kind = str(data["kind"])
        ts = float(data["ts"])
        chunks_dir = Path(str(data["chunks_dir"]))
        stem = f"ch{channel}_{kind}_{seq:06d}"
        npy_path = chunks_dir / f"{stem}.npy"
        meta_path = chunks_dir / f"{stem}.json"
        block = np.asarray(data["block"], dtype=np.float32)

        np.save(npy_path, block)
        meta = {
            "seq": seq,
            "channel": channel,
            "kind": kind,
            "ts": ts,
            "cfg_scan_rate": data["cfg_scan_rate"],
            "cfg_mode": data["cfg_mode"],
            "cfg_pulse_width": data["cfg_pulse_width"],
            "cfg_scale_down": data["cfg_scale_down"],
            "cb_lines": data["cb_lines"],
            "point_count": data["point_count"],
            "shape": list(block.shape),
        }
        self._write_json(meta_path, meta)
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + "\n")

        bytes_written = npy_path.stat().st_size + meta_path.stat().st_size
        with self._lock:
            self._written_blocks += 1
            self._written_bytes += int(bytes_written)

    @staticmethod
    def _enqueue_control(queue_obj: queue.Queue, item):
        while True:
            try:
                queue_obj.put_nowait(item)
                return
            except queue.Full:
                try:
                    queue_obj.get_nowait()
                except queue.Empty:
                    return

    @staticmethod
    def _write_json(path: Path, payload: dict):
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _format_bytes(size: int) -> str:
        value = float(max(0, int(size)))
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024.0 or unit == "GB":
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{value:.1f} GB"
