import struct
import sys

from pymodbus.client import ModbusSerialClient as ModbusClient

from ..core import get_logger
from ..core.config import (
    watlow_ir_baudrate,
    watlow_ir_bytesize,
    watlow_ir_parity,
    watlow_ir_port,
    watlow_ir_stopbits,
    watlow_ir_timeout_s,
)


logger = get_logger(__name__)


class WatlowController:
    """Watlow IR temperature controller helper."""

    def __init__(self) -> None:
        self.watlow_client = None

    def connect_watlow_ir(self, port=watlow_ir_port) -> None:
        """Connect to a Modbus device."""
        self.watlow_client = ModbusClient(
            port=port,
            baudrate=watlow_ir_baudrate,
            parity=watlow_ir_parity,
            stopbits=watlow_ir_stopbits,
            bytesize=watlow_ir_bytesize,
            timeout=watlow_ir_timeout_s,
        )
        logger.info("Connected to Watlow IR on %s", port)
        if not self.watlow_client.connect():
            logger.error("Unable to connect to Watlow IR Modbus serial device")
            self.watlow_client = None

    def readTemp_ir(self, address=360, slave_id=1) -> float:
        """Read temperature from Modbus device.

        address 2172: Read set temperature
        """
        if not self.watlow_client:
            logger.error("Modbus client not connected.")
            return None

        result = self.watlow_client.read_holding_registers(
            address=address, count=2
        )  # , slave=slave_id)
        if result.isError():
            logger.error("Error reading the temperature registers")
            return None

        registers = result.registers
        registers_bytes = struct.pack(">HH", registers[1], registers[0])
        temperature = struct.unpack(">f", registers_bytes)
        temperature_c = round(self.f2c(int(temperature[0])), 1)

        if not (0 < temperature_c < 1000):
            result = self.watlow_client.read_holding_registers(
                address=362, count=2
            )  # , slave=slave_id)
            if result.isError():
                logger.error("Error reading the temperature registers")
                return None
            registers = result.registers
            logger.error("Error reading temperature. Error code: %s", registers[0])

            self.setTemp_ir(25)  # Reset to a default temperature

            result = self.watlow_client.read_holding_registers(
                address=2172, count=2
            )  # , slave=slave_id)
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

    def setTemp_ir(self, set_point, address=2160, slave_id=1):
        """Set the target temperature on the Modbus device."""
        if not self.watlow_client:
            logger.error("Modbus client not connected.")
            return False
        data_bytes = struct.pack(">f", self.c2f(set_point))
        reg_hi, reg_lo = struct.unpack(">HH", data_bytes)
        result = self.watlow_client.write_registers(
            address=address, values=[reg_lo, reg_hi]
        )  # , slave=slave_id)
        if result.isError():
            logger.error("Error setting temperature")
            return False
        return True

    def f2c(self, fahrenheit):
        return (fahrenheit - 32) * 5 / 9

    def c2f(self, celcius):
        return (celcius * 9 / 5) + 32
