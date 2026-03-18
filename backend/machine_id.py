from __future__ import annotations

import hashlib
import socket
import uuid
from pathlib import Path


def _first_readable_text(paths: list[str]) -> str:
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            continue
        if text:
            return text
    return ""


def get_machine_id() -> str:
    """Return a short, stable machine identifier for this Linux installation."""
    parts = []

    machine_id = _first_readable_text(
        [
            "/etc/machine-id",
            "/var/lib/dbus/machine-id",
        ]
    )
    if machine_id:
        parts.append(f"machine-id:{machine_id}")

    mac_value = uuid.getnode()
    if mac_value:
        parts.append(f"mac:{mac_value:012x}")

    hostname = socket.gethostname().strip()
    if hostname:
        parts.append(f"hostname:{hostname}")

    if not parts:
        parts.append("unknown-machine")

    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest().upper()
    return f"JMV-{digest[:12]}"
