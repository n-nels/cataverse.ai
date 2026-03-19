import struct
import time
from datetime import datetime

from pymodbus.client import ModbusSerialClient as ModbusClient

from ..core import get_logger
from ..core.config import (
    extrel_ms_baudrate,
    extrel_ms_bytesize,
    extrel_ms_parity,
    extrel_ms_port,
    extrel_ms_stopbits,
    extrel_ms_timeout_s,
)


logger = get_logger(__name__)


class ExtrelMassSpec:
    """Extrel mass spectrometer helper."""

    def __init__(self) -> None:
        self.extrel_client = None

    def connect_extrel(self, port=extrel_ms_port) -> None:
        """Connect to the Extrel device."""
        self.extrel_client = ModbusClient(
            port=port,
            baudrate=extrel_ms_baudrate,
            parity=extrel_ms_parity,
            stopbits=extrel_ms_stopbits,
            bytesize=extrel_ms_bytesize,
            timeout=extrel_ms_timeout_s,
        )
        logger.info("Connected to Extrel MS on %s", port)
        if not self.extrel_client.connect():
            logger.error("Unable to connect to Extrel Modbus serial device")
            self.extrel_client = None

    def extrel_read(self, address, count=1, unit=1):
        """Read from Extrel device."""
        result = self.extrel_client.read_holding_registers(
            address=address, count=count, device_id=unit
        )
        if result.isError():
            logger.error("Error reading from Extrel device")
            return None
        registers = result.registers
        return registers

    def extrel_write(self, address, value):
        """Write a value to an Extrel holding register."""
        result = self.extrel_client.write_register(address=address, value=value)
        if result.isError():
            logger.error("Error writing to Extrel device.")
            logger.error("Modbus Exception: %s", result)
            return False
        return True

    def decode_ieee754_cdab(self, r0, r1):
        """Decode two Modbus registers (r0, r1) in CDAB order to a float."""
        raw = r1.to_bytes(2, "big") + r0.to_bytes(2, "big")
        return struct.unpack(">f", raw)[0]

    def extrel_stream_test(self, start_address=2, polls=10, poll_interval=1.5, unit=1):
        """
        Reads 4 Paired+IEEE754 values in one contiguous block:
        start_address=2 -> reads registers 2..9 (8 regs) -> tags at 2,4,6,8

        Tag order:
        V1_I_28, V1_I_29, V1_I_44, V1_I_45
        """
        tags = ["V1_I_28", "V1_I_29", "V1_I_44", "V1_I_45"]

        for i in range(polls):
            rr = self.extrel_client.read_holding_registers(
                address=start_address, count=8, device_id=unit
            )

            if rr.isError():
                logger.error("%s: read error: %s", i, rr)
            else:
                regs = rr.registers  # 8 regs total
                vals = [
                    self.decode_ieee754_cdab(regs[0], regs[1]),
                    self.decode_ieee754_cdab(regs[2], regs[3]),
                    self.decode_ieee754_cdab(regs[4], regs[5]),
                    self.decode_ieee754_cdab(regs[6], regs[7]),
                ]

                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # milliseconds
                logger.info(
                    f"{ts} | "
                    f"{tags[0]}={vals[0]:.6g} | {tags[1]}={vals[1]:.6g} | "
                    f"{tags[2]}={vals[2]:.6g} | {tags[3]}={vals[3]:.6g}"
                )

            time.sleep(poll_interval)

        return True
