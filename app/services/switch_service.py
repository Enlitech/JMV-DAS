from __future__ import annotations

from backend.optical_switch import Gezhi12SwitchController


class SwitchService:
    def __init__(self, controller: Gezhi12SwitchController | None = None):
        self.controller = controller or Gezhi12SwitchController()

    @property
    def is_open(self) -> bool:
        return self.controller.is_open

    @property
    def port_name(self) -> str:
        return self.controller.port_name

    def available_ports(self) -> list[str]:
        return self.controller.available_ports()

    def open(self, port_name: str):
        self.controller.open(port_name)

    def close(self):
        self.controller.close()

    def current_fibre(self, channel: int) -> str:
        return self.controller.current_fibre(channel)

    def set_fibre(self, channel: int, fibre_name: str):
        self.controller.set_fibre(channel, fibre_name)

    def set_fibres(self, ch1_fibre: str, ch2_fibre: str):
        self.controller.set_fibres(ch1_fibre, ch2_fibre)

    def set_assumed_fibres(self, ch1_fibre: str, ch2_fibre: str):
        self.controller.set_assumed_fibre(1, ch1_fibre)
        self.controller.set_assumed_fibre(2, ch2_fibre)

    def snapshot(self) -> dict[int, str]:
        return {
            1: self.current_fibre(1),
            2: self.current_fibre(2),
        }
