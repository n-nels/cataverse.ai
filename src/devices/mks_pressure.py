import time
from datetime import datetime

import serial

from ..core import get_logger
from ..core.config import mks_serial_baudrate, mks_serial_port, mks_serial_timeout_s


logger = get_logger(__name__)


class MKSPressureGauge:
    """MKS pressure gauge communication helper."""

    def __init__(self) -> None:
        self.mks_com = mks_serial_port
        self.mks_connection = None

    def connect_mks(self) -> None:
        """Establishes a connection to the MKS PDR2000 device."""
        try:
            self.mks_connection = serial.Serial(
                self.mks_com,
                baudrate=mks_serial_baudrate,
                timeout=mks_serial_timeout_s,
            )
            logger.info("Connected to MKS PDR2000 on %s", self.mks_com)
        except Exception as e:
            logger.error("Failed to connect to %s: %s", self.mks_com, e)

    def read_pressure(self, command: str = "p") -> tuple:
        """Reads pressure from the MKS PDR2000 device."""
        if self.mks_connection and self.mks_connection.is_open:
            try:
                self.mks_connection.write(command.encode("utf-8"))
                response = self.mks_connection.readline().decode("utf-8").strip()
                p1 = response.split(" ")[0]
                p2 = response.split(" ")[-1]
            except Exception as e:
                logger.error("Error sending command %s to %s: %s", command, self.mks_com, e)
                try:
                    self.disconnect()
                    time.sleep(2)
                    self.connect_mks()
                    time.sleep(2)
                    self.mks_connection.write(command.encode("utf-8"))
                    response = self.mks_connection.readline().decode("utf-8").strip()
                    p1 = response.split(" ")[0]
                    p2 = response.split(" ")[-1]
                except Exception as e:
                    logger.error("Error after reconnecting to %s: %s", self.mks_com, e)
                    return datetime.now(), None, None
            try:
                return datetime.now(), float(p1), float(p2)
            except ValueError:
                try:
                    return datetime.now(), float(p1), str(p2)
                except ValueError:
                    return datetime.now(), str(p1), str(p2)
        else:
            logger.warning("Serial connection not established.")
            self.connect_mks()

    def disconnect(self) -> None:
        if self.mks_connection and self.mks_connection.is_open:
            self.mks_connection.close()
            logger.info("Disconnected MKS.")
