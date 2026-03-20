"""Extrel mass spectrometer Modbus adapter for the hardware layer.

This module ports low-level Extrel register read/write/decoding behavior from
the legacy device helper while accepting an injected Modbus client connection.
"""

from __future__ import annotations

import logging
import struct
from typing import Any

from pymodbus.client import ModbusSerialClient as ModbusClient


logger = logging.getLogger(__name__)


class ExtrelMassSpec:
    """Low-level Extrel MS communication using an injected Modbus client."""

    def __init__(self, client: ModbusClient | None) -> None:
        self.client = client

    def read_registers(
        self,
        address: int,
        count: int = 1,
        unit: int = 1,
    ) -> list[int] | None:
        """Read holding registers from Extrel MS."""

        if not self.client:
            return None

        result = self.client.read_holding_registers(
            address=address,
            count=count,
            device_id=unit,
        )
        if result.isError():
            logger.error("Error reading from Extrel device")
            return None

        return result.registers

    def write_register(self, address: int, value: int) -> bool:
        """Write one holding register on Extrel MS."""

        if not self.client:
            return False

        result = self.client.write_register(address=address, value=value)
        if result.isError():
            logger.error("Error writing to Extrel device.")
            logger.error("Modbus Exception: %s", result)
            return False

        return True

    @staticmethod
    def decode_ieee754_cdab(r0: int, r1: int) -> float:
        """Decode two Modbus registers (r0, r1) in CDAB order to float."""

        raw = r1.to_bytes(2, "big") + r0.to_bytes(2, "big")
        return struct.unpack(">f", raw)[0]
