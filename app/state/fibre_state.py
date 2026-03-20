from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FibreMonitorConfig:
    monitor_channel: int = 1
    spatial_ewma_alpha: float = 0.2
    threshold: float = 1000.0
    min_length_m: float = 100.0
    default_fibre: str = "main"
    enable_alarm: bool = True
    enable_autoswitch: bool = False
    enable_peek: bool = False
    peek_interval: int = 20
    peek_delay_ms: int = 200


@dataclass
class SwitchAction:
    channel: int
    fibre_name: str
    reason: str
    detail: str
    reset_peek_counter: bool = False


@dataclass
class FibreMonitorView:
    text: str
    alarm: bool = False
