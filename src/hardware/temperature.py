"""Watlow temperature controller adapter for the hardware layer.

This module ports low-level Modbus temperature read/write behavior from the
legacy device helper while accepting an injected Modbus client connection.
"""

from __future__ import annotations

import logging
import struct
import sys

from pymodbus.client import ModbusSerialClient as ModbusClient


logger = logging.getLogger(__name__)


class WatlowTemperature:
    """Low-level Watlow IR temperature adapter using injected Modbus client."""

    def __init__(self, client: ModbusClient) -> None:
        self.client = client

    def read_temperature(self, address: int = 360) -> float | None:
        """Read temperature from Modbus controller and return Celsius."""

        if not self.client:
            logger.error("Modbus client not connected.")
            return None

        result = self.client.read_holding_registers(
            address=address,
            count=2,
        )
        if result.isError():
            logger.error("Error reading the temperature registers")
            return None

        registers = result.registers
        registers_bytes = struct.pack(">HH", registers[1], registers[0])
        temperature = struct.unpack(">f", registers_bytes)
        temperature_c = round(self.f2c(int(temperature[0])), 1)

        if not (0 < temperature_c < 1000):
            result = self.client.read_holding_registers(
                address=362,
                count=2,
            )
            if result.isError():
                logger.error("Error reading the temperature registers")
                return None

            registers = result.registers
            logger.error("Error reading temperature. Error code: %s", registers[0])

            self.set_temperature(25)  # Reset to a default temperature

            result = self.client.read_holding_registers(
                address=2172,
                count=2,
            )
            if result.isError():
                logger.error("Error reading the temperature registers")
                return None

            registers = result.registers
            registers_bytes = struct.pack(">HH", registers[1], registers[0])
            set_temperature = struct.unpack(">f", registers_bytes)[0]
            set_temperature_c = round(self.f2c(int(set_temperature)), 1)
            logger.error("Set temperature is: %s C", set_temperature_c)
            sys.exit("Exiting due to temperature read error.")

        return temperature_c

    def set_temperature(
        self,
        setpoint: float,
        address: int = 2160,
        slave_id: int = 1,
    ) -> bool:
        """Set target temperature on the Modbus controller."""

        if not self.client:
            logger.error("Modbus client not connected.")
            return False

        data_bytes = struct.pack(">f", self.c2f(setpoint))
        reg_hi, reg_lo = struct.unpack(">HH", data_bytes)
        result = self.client.write_registers(
            address=address,
            values=[reg_lo, reg_hi],
        )  # , slave=slave_id)
        if result.isError():
            logger.error("Error setting temperature")
            return False

        return True

    @staticmethod
    def f2c(fahrenheit: float) -> float:
        """Convert Fahrenheit to Celsius."""

        return (fahrenheit - 32) * 5 / 9

    @staticmethod
    def c2f(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""

        return (celsius * 9 / 5) + 32
