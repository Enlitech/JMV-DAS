from __future__ import annotations

import json
from urllib import error, request


class VibRecService:
    def __init__(self, base_url: str = "http://192.168.3.252:8000", timeout_s: float = 10.0):
        self.base_url = self._normalize_base_url(base_url)
        self.timeout_s = max(0.5, float(timeout_s))

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        text = str(base_url or "").strip()
        if not text:
            text = "http://192.168.3.252:8000"
        if not text.startswith(("http://", "https://")):
            text = f"http://{text}"
        return text.rstrip("/")

    def set_base_url(self, base_url: str):
        self.base_url = self._normalize_base_url(base_url)

    def health(self) -> dict:
        return self._request_json("GET", "/api/v1/health")

    def schema(self) -> dict:
        return self._request_json("GET", "/api/v1/predict/actor/schema")

    def predict_actor_raw(self, payload: dict) -> dict:
        return self._request_json("POST", "/api/v1/predict/actor/raw", payload=payload)

    def _request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response from {url}") from exc
