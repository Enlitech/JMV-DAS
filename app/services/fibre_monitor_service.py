from __future__ import annotations

import time
from dataclasses import replace

import numpy as np

from app.state.fibre_state import FibreMonitorConfig, FibreMonitorView, SwitchAction
from backend.fibre_break_detector import FibreBreakDetector


class FibreMonitorService:
    def __init__(self, channels: tuple[int, ...] = (1, 2)):
        self.channels = tuple(sorted({int(ch) for ch in channels}))
        self.detectors = {ch: FibreBreakDetector() for ch in self.channels}
        self.config = FibreMonitorConfig(
            monitor_channel=self.channels[0] if self.channels else 1,
        )
        self._peek_state = "idle"
        self._peek_target_fibre = "main"
        self._peek_return_fibre = "main"
        self._peek_ready_ts = 0.0
        self._peek_counter = self.config.peek_interval
        self._result_by_channel = {ch: None for ch in self.channels}
        self._health_by_channel = {ch: {"main": None, "standby": None} for ch in self.channels}
        self._result_by_fibre = {ch: {"main": None, "standby": None} for ch in self.channels}
        self._apply_detector_config()

    @staticmethod
    def normalize_fibre_name(value: str, default: str = "main") -> str:
        name = (value or "").strip().lower()
        if name in {"standby", "on"}:
            return "standby"
        if name in {"main", "off"}:
            return "main"
        return default

    @staticmethod
    def other_fibre_name(fibre_name: str) -> str:
        return "standby" if FibreMonitorService.normalize_fibre_name(fibre_name) == "main" else "main"

    @staticmethod
    def channel_name_for_api(channel: int) -> str:
        return f"ch{int(channel)}"

    def alert_name_for_channel(self, channel: int) -> str:
        return f"fibre_break_{self.channel_name_for_api(channel)}"

    def configure(self, **kwargs):
        cfg = replace(self.config, **kwargs)
        cfg.default_fibre = self.normalize_fibre_name(cfg.default_fibre)
        cfg.monitor_channel = self.channels[0] if int(cfg.monitor_channel) not in self.channels else int(cfg.monitor_channel)
        cfg.peek_interval = max(1, int(cfg.peek_interval))
        cfg.peek_delay_ms = max(0, int(cfg.peek_delay_ms))
        self.config = cfg
        self._apply_detector_config()

    def reset(self):
        for detector in self.detectors.values():
            detector.reset()
        self._result_by_channel = {ch: None for ch in self.channels}
        self._health_by_channel = {ch: {"main": None, "standby": None} for ch in self.channels}
        self._result_by_fibre = {ch: {"main": None, "standby": None} for ch in self.channels}
        self.cancel_peek(reset_counter=True)

    def cancel_peek(self, reset_counter: bool = False):
        self._peek_state = "idle"
        self._peek_ready_ts = 0.0
        if reset_counter:
            self._peek_counter = int(self.config.peek_interval)

    def process_amp_payload(
        self,
        payload: dict,
        current_fibres: dict[int, str],
        switch_connected: bool,
    ) -> list[SwitchAction]:
        if str(payload.get("kind", "")) != "amp":
            return []

        ch = int(payload.get("channel", 1))
        if ch not in self.channels:
            return []

        block = np.asarray(payload.get("block"), dtype=np.float32)
        if block.ndim != 2 or block.size == 0:
            return []

        self._apply_detector_config()
        scale_down = int(payload.get("cfg_scale_down", 1) or 1)
        now_mono = time.monotonic()
        current_fibre = self.normalize_fibre_name(current_fibres.get(ch, "main"))
        detector = self.detectors[ch]
        health_map = self._health_by_channel[ch]
        result_map = self._result_by_fibre[ch]

        if ch != self.config.monitor_channel:
            result = detector.update(block, scale_down=scale_down, fibre_name=current_fibre)
            self._result_by_channel[ch] = result
            result_map[current_fibre] = result
            health_map[current_fibre] = result.healthy
            return []

        if self._peek_state == "waiting_other":
            if current_fibre != self._peek_target_fibre or now_mono < self._peek_ready_ts:
                return []

            other_result = detector.update(
                block,
                scale_down=scale_down,
                fibre_name=self._peek_target_fibre,
            )
            result_map[self._peek_target_fibre] = other_result
            health_map[self._peek_target_fibre] = other_result.healthy
            self._peek_state = "waiting_restore"
            self._peek_ready_ts = now_mono + max(0.0, self.config.peek_delay_ms / 1000.0)
            return [
                SwitchAction(
                    channel=ch,
                    fibre_name=self._peek_return_fibre,
                    reason="peek_return",
                    detail=(
                        f"Peeked {self._peek_target_fibre} and returned to "
                        f"{self._peek_return_fibre} on CH{ch}"
                    ),
                )
            ]

        if self._peek_state == "waiting_restore":
            if current_fibre != self._peek_return_fibre or now_mono < self._peek_ready_ts:
                return []
            self._peek_state = "idle"
            self._peek_ready_ts = 0.0

        active_fibre = current_fibre
        result = detector.update(block, scale_down=scale_down, fibre_name=active_fibre)
        self._result_by_channel[ch] = result
        result_map[active_fibre] = result
        health_map[active_fibre] = result.healthy

        auto_action = self._maybe_auto_switch_current_fibre(ch, active_fibre)
        if auto_action is not None:
            return [auto_action]

        peek_action = self._maybe_queue_other_fibre_peek(ch, active_fibre, switch_connected)
        if peek_action is not None:
            return [peek_action]

        return []

    def status_view(self, current_fibres: dict[int, str], display_name, format_length) -> FibreMonitorView:
        monitor_ch = self.config.monitor_channel
        active_fibre = self.normalize_fibre_name(current_fibres.get(monitor_ch, "main"))
        other_fibre = self.other_fibre_name(active_fibre)
        health_map = self._health_by_channel[monitor_ch]
        result = self._result_by_channel.get(monitor_ch)

        peeking_text = "idle"
        if self._peek_state == "waiting_other":
            peeking_text = f"peeking {display_name(self._peek_target_fibre)}"
        elif self._peek_state == "waiting_restore":
            peeking_text = f"returning to {display_name(self._peek_return_fibre)}"

        if result is None:
            return FibreMonitorView(
                text=(
                    f"Fibre Break ch{monitor_ch}/amp: waiting for data, "
                    f"active={display_name(active_fibre)}, "
                    f"other={display_name(other_fibre)}({self.health_text(health_map[other_fibre])}), "
                    f"default={display_name(self.config.default_fibre)}, peek={peeking_text}"
                ),
                alarm=False,
            )

        return FibreMonitorView(
            text=(
                f"Fibre Break ch{monitor_ch}/amp: {'ALARM' if result.abnormal else 'Normal'}, "
                f"sample={display_name(result.fibre_name)}, "
                f"active={display_name(active_fibre)}({self.health_text(health_map[active_fibre])}), "
                f"other={display_name(other_fibre)}({self.health_text(health_map[other_fibre])}), "
                f"length={format_length(result.first_high_distance_m)}, "
                f"last_high_pos={result.first_high_pos}, "
                f"threshold={result.threshold:.3f}, min_len={result.min_length_m:.2f} m, "
                f"default={display_name(self.config.default_fibre)}, "
                f"peek={peeking_text}, "
                f"autoswitch={'ON' if self.config.enable_autoswitch else 'OFF'}"
            ),
            alarm=self.config.enable_alarm and result.abnormal,
        )

    def build_alert_status_payload(self, channel: int, current_fibres: dict[int, str]) -> dict:
        channel = int(channel)
        active_fibre = self.normalize_fibre_name(current_fibres.get(channel, "main"))
        other_fibre = self.other_fibre_name(active_fibre)
        active_result = self._result_by_fibre[channel].get(active_fibre)
        health_map = self._health_by_channel[channel]

        first_high_pos = -1
        first_high_distance_m = -1.0
        abnormal = False
        if active_result is not None:
            first_high_pos = int(active_result.first_high_pos)
            first_high_distance_m = float(active_result.first_high_distance_m)
            abnormal = bool(active_result.abnormal)

        return {
            "name": self.alert_name_for_channel(channel),
            "type": "fibre_break",
            "channel": self.channel_name_for_api(channel),
            "metric": "amp",
            "ts_wall_ms": int(time.time() * 1000),
            "abnormal": abnormal,
            "active_healthy": self.api_bool(health_map.get(active_fibre)),
            "other_healthy": self.api_bool(health_map.get(other_fibre)),
            "threshold": float(self.config.threshold),
            "least_len": float(self.config.min_length_m),
            "first_high_pos": first_high_pos,
            "first_high_distance_m": first_high_distance_m,
            "active_fibre": active_fibre,
            "other_fibre": other_fibre,
            "is_peeking_other": channel == self.config.monitor_channel and self._peek_state != "idle",
            "is_autoswitch_enabled": bool(self.config.enable_autoswitch),
            "peek_time_interval_ms": int(self.config.peek_delay_ms),
            "peek_interval_multiple": int(self.config.peek_interval),
            "default_fibre_name": self.config.default_fibre,
            "relay_id": max(0, channel - 1),
            "switch_id": 0,
            "fibre_names": ["main", "standby"],
        }

    def build_fibre_health_entry(self, channel: int, current_fibres: dict[int, str]) -> dict:
        channel = int(channel)
        active_fibre = self.normalize_fibre_name(current_fibres.get(channel, "main"))
        other_fibre = self.other_fibre_name(active_fibre)
        active_result = self._result_by_fibre[channel].get(active_fibre)
        health_map = self._health_by_channel[channel]

        current_first_high_distance = -1.0
        if active_result is not None:
            current_first_high_distance = float(active_result.first_high_distance_m)

        return {
            "channel_name": self.channel_name_for_api(channel),
            "is_healthy": self.api_bool(health_map.get(active_fibre)),
            "current_first_high_distance": current_first_high_distance,
            "current_fibre": active_fibre,
            "is_healthy_other": self.api_bool(health_map.get(other_fibre)),
            "other_fibre": other_fibre,
            "is_peeking_other": channel == self.config.monitor_channel and self._peek_state != "idle",
            "is_autoswitch_enabled": bool(self.config.enable_autoswitch),
            "peek_time_interval_ms": int(self.config.peek_delay_ms),
            "peek_other_fibre_interval_multiple": int(self.config.peek_interval),
            "fibre_names": ["main", "standby"],
        }

    def build_api_snapshot(self, machine_id: str, current_fibres: dict[int, str]) -> dict:
        alert_payloads = {
            self.alert_name_for_channel(channel): self.build_alert_status_payload(channel, current_fibres)
            for channel in self.channels
        }
        return {
            "machine_id": machine_id,
            "channel_count": len(self.channels),
            "alerts": [
                {
                    "alert_name": self.alert_name_for_channel(channel),
                    "type": "fibre_break",
                }
                for channel in self.channels
            ],
            "alert_status_by_name": alert_payloads,
            "fibre_health": [self.build_fibre_health_entry(channel, current_fibres) for channel in self.channels],
        }

    @staticmethod
    def health_text(value) -> str:
        if value is True:
            return "healthy"
        if value is False:
            return "broken"
        return "unknown"

    @staticmethod
    def api_bool(value) -> bool:
        return bool(value is True)

    def _apply_detector_config(self):
        for detector in self.detectors.values():
            detector.configure(
                spatial_ewma_alpha=float(self.config.spatial_ewma_alpha),
                threshold=float(self.config.threshold),
                min_length_m=float(self.config.min_length_m),
            )

    def _maybe_auto_switch_current_fibre(self, channel: int, active_fibre: str) -> SwitchAction | None:
        if not self.config.enable_autoswitch:
            return None

        default_fibre = self.config.default_fibre
        other_fibre = self.other_fibre_name(active_fibre)
        health_map = self._health_by_channel[channel]
        healthy_cur = health_map.get(active_fibre)
        healthy_other = health_map.get(other_fibre)
        healthy_default = health_map.get(default_fibre)

        target_fibre = active_fibre
        if healthy_cur is False:
            if healthy_default is True:
                target_fibre = default_fibre
            elif healthy_other is True:
                target_fibre = other_fibre
        elif active_fibre != default_fibre and healthy_default is True:
            target_fibre = default_fibre

        if target_fibre == active_fibre:
            return None

        self.cancel_peek(reset_counter=True)
        return SwitchAction(
            channel=int(channel),
            fibre_name=target_fibre,
            reason="auto_switch",
            detail=f"Auto switched CH{channel} to {target_fibre}",
            reset_peek_counter=True,
        )

    def _maybe_queue_other_fibre_peek(
        self,
        channel: int,
        active_fibre: str,
        switch_connected: bool,
    ) -> SwitchAction | None:
        if not self.config.enable_peek or self._peek_state != "idle":
            return None

        interval = max(1, int(self.config.peek_interval))
        if self._peek_counter < interval:
            self._peek_counter += 1
            return None

        if not switch_connected:
            return None

        other_fibre = self.other_fibre_name(active_fibre)
        self._peek_state = "waiting_other"
        self._peek_target_fibre = other_fibre
        self._peek_return_fibre = active_fibre
        self._peek_ready_ts = time.monotonic() + max(0.0, self.config.peek_delay_ms / 1000.0)
        self._peek_counter = 0
        return SwitchAction(
            channel=int(channel),
            fibre_name=other_fibre,
            reason="peek_start",
            detail=f"Peeking {other_fibre} on CH{channel}",
        )
