from __future__ import annotations

import serial
from serial.tools import list_ports


class Gezhi12SwitchController:
    """Direct RS485 controller for a 2-channel GEZHI12 optical switch."""

    CHANNEL_COILS = {
        1: 0x0000,
        2: 0x0003,
    }

    def __init__(self, baudrate: int = 9600, slave_id: int = 0xFF, timeout: float = 1.0):
        self.baudrate = int(baudrate)
        self.slave_id = int(slave_id) & 0xFF
        self.timeout = float(timeout)
        self.port: serial.Serial | None = None
        self.port_name = ""

    @staticmethod
    def available_ports() -> list[str]:
        return [info.device for info in list_ports.comports()]

    @property
    def is_open(self) -> bool:
        return self.port is not None and self.port.is_open

    def open(self, port_name: str):
        name = (port_name or "").strip()
        if not name:
            raise ValueError("Serial port name is required.")

        self.close()
        self.port = serial.Serial(
            port=name,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )
        self.port_name = name

    def close(self):
        if self.port is not None:
            try:
                self.port.close()
            finally:
                self.port = None
                self.port_name = ""

    def set_channel(self, channel: int, enabled: bool):
        coil_addr = self.CHANNEL_COILS.get(int(channel))
        if coil_addr is None:
            raise ValueError(f"Unsupported switch channel: {channel}")

        command = self._build_single_coil_command(coil_addr, bool(enabled))
        self._send_and_validate(command)

    def set_channels(self, ch1_enabled: bool, ch2_enabled: bool):
        self.set_channel(1, ch1_enabled)
        self.set_channel(2, ch2_enabled)

    def _send_and_validate(self, command: bytes):
        if not self.is_open or self.port is None:
            raise RuntimeError("Switch serial port is not connected.")

        self.port.reset_input_buffer()
        self.port.write(command)
        self.port.flush()

        response = self.port.read(len(command))
        if len(response) != len(command):
            raise RuntimeError(
                f"Incomplete RS485 response: expected {len(command)} bytes, got {len(response)}."
            )

        if response != command:
            raise RuntimeError(
                f"Unexpected RS485 response: sent={command.hex(' ')} recv={response.hex(' ')}"
            )

    def _build_single_coil_command(self, coil_addr: int, enabled: bool) -> bytes:
        payload = bytes(
            [
                self.slave_id,
                0x05,
                (coil_addr >> 8) & 0xFF,
                coil_addr & 0xFF,
                0xFF if enabled else 0x00,
                0x00,
            ]
        )
        crc = self._crc16_modbus(payload)
        return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    @staticmethod
    def _crc16_modbus(data: bytes) -> int:
        crc = 0xFFFF
        for value in data:
            crc ^= value
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF
