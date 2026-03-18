from __future__ import annotations

import copy
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class CompatHttpApiServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8009):
        self.host = str(host)
        self.port = int(port)
        self._server: _ReusableThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._snapshot = {
            "machine_id": "",
            "channel_count": 0,
            "alerts": [],
            "alert_status_by_name": {},
            "fibre_health": [],
        }
        self._last_error = ""

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> bool:
        if self.is_running:
            return True

        handler_cls = self._build_handler_class()
        try:
            self._server = _ReusableThreadingHTTPServer((self.host, self.port), handler_cls)
        except OSError as exc:
            self._server = None
            self._thread = None
            self._last_error = str(exc)
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="compat-http-api",
            daemon=True,
        )
        self._thread.start()
        self._last_error = ""
        return True

    def stop(self):
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def set_snapshot(self, snapshot: dict):
        with self._lock:
            self._snapshot = copy.deepcopy(snapshot)

    def get_snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def _build_handler_class(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "JMV-DAS"
            sys_version = ""

            def log_message(self, format: str, *args):
                return

            def do_OPTIONS(self):
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_common_headers("application/json; charset=utf-8")
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query, keep_blank_values=True)
                snapshot = api.get_snapshot()

                if parsed.path == "/":
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "name": "JMV-DAS compatibility API",
                            "port": api.port,
                            "machine_id": snapshot.get("machine_id", ""),
                        },
                    )
                    return

                if parsed.path == "/info":
                    self._handle_info(query, snapshot)
                    return

                if parsed.path == "/fibre_status":
                    self._handle_fibre_status(query, snapshot)
                    return

                if parsed.path == "/alert":
                    self._handle_alert(query, snapshot)
                    return

                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def _handle_info(self, query: dict[str, list[str]], snapshot: dict):
                kind = self._query_value(query, "kind", "all")
                machine_id = str(snapshot.get("machine_id", "") or "")
                if kind == "machine_id":
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "kind": "machine_id",
                            "hash": machine_id,
                        },
                    )
                    return

                if kind == "all":
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "kind": "all",
                            "channel_count": int(snapshot.get("channel_count", 0) or 0),
                            "machine_id": {
                                "hash": machine_id,
                            },
                        },
                    )
                    return

                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Info Failed"})

            def _handle_fibre_status(self, query: dict[str, list[str]], snapshot: dict):
                kind = self._query_value(query, "kind", "")
                if not kind:
                    self._write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Invalid argument (no kind)"},
                    )
                    return

                if kind == "health":
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "fibre_health": snapshot.get("fibre_health", []),
                        },
                    )
                    return

                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Fibre Status Failed"})

            def _handle_alert(self, query: dict[str, list[str]], snapshot: dict):
                kind = self._query_value(query, "kind", "")
                if not kind:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "missing kind"})
                    return

                if kind == "list":
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "alerts": snapshot.get("alerts", []),
                        },
                    )
                    return

                alert_name = self._query_value(query, "alert_name", "")
                if not alert_name:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "missing alert_name"})
                    return

                if kind == "status":
                    alert_map = snapshot.get("alert_status_by_name", {})
                    status = alert_map.get(alert_name)
                    if status is None:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "alert not found"})
                        return
                    self._write_json(HTTPStatus.OK, status)
                    return

                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid kind"})

            @staticmethod
            def _query_value(query: dict[str, list[str]], key: str, default: str) -> str:
                values = query.get(key)
                if not values:
                    return default
                return str(values[0])

            def _write_json(self, status: HTTPStatus, payload):
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(int(status))
                self._send_common_headers("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_common_headers(self, content_type: str):
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")

        return Handler
