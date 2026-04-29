"""MKS pressure gauge adapter for the new hardware layer.

This module provides low-level pressure reads from an injected serial
connection and preserves the legacy reconnect-on-failure behavior.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import NamedTuple

import serial

from src.hardware.errors import HardwareConnectionError, HardwareReadError


logger = logging.getLogger(__name__)


class PressureReading(NamedTuple):
    """One pressure read from the MKS gauge."""

    timestamp: datetime
    manifold: float | None
    cell: float | None


class MKSPressure:
    """Low-level MKS pressure communication using an injected serial connection."""

    def __init__(self, connection: serial.Serial) -> None:
        self.connection = connection
        self._serial_cls = serial.Serial
        self._port: str | None = getattr(connection, "port", None)
        self._baudrate: int | None = getattr(connection, "baudrate", None)
        self._timeout: float | None = getattr(connection, "timeout", None)

    def _connect_once(self) -> bool:
        """Connect once using cached serial settings (no reconnect delay)."""

        if self._port is None or self._baudrate is None:
            raise HardwareConnectionError(
                "Missing serial connection settings for MKS reconnect"
            )

        try:
            self.connection = self._serial_cls(
                self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
            return True
        except Exception as exc:
            logger.error("Failed to connect to %s: %s", self._port, exc)
            return False

    def _reconnect(self) -> bool:
        """Reconnect once using existing connection settings when available."""

        try:
            self.disconnect()
            time.sleep(2)
            if not self._connect_once():
                return False
            time.sleep(2)
            return True
        except Exception as exc:
            logger.error("Error after reconnecting to MKS: %s", exc)
            return False

    def read(self, command: str = "p") -> PressureReading:
        """Read manifold/cell pressure values from MKS gauge."""

        if self.connection and self.connection.is_open:
            try:
                self.connection.write(command.encode("utf-8"))
                response = self.connection.readline().decode("utf-8").strip()
                p1 = response.split(" ")[0]
                p2 = response.split(" ")[-1]
            except Exception as exc:
                logger.error("Error sending command %s to %s: %s", command, self._port, exc)
                if not self._reconnect():
                    time.sleep(2)
                    return PressureReading(datetime.now(), None, None)
                try:
                    self.connection.write(command.encode("utf-8"))
                    response = self.connection.readline().decode("utf-8").strip()
                    p1 = response.split(" ")[0]
                    p2 = response.split(" ")[-1]
                except Exception as reconnect_exc:
                    logger.error("Error after reconnecting to %s: %s", self._port, reconnect_exc)
                    return PressureReading(datetime.now(), None, None)

            try:
                return PressureReading(datetime.now(), float(p1), float(p2))
            except ValueError:
                raise HardwareReadError(
                    f"MKS gauge returned non-numeric (over-range?) data: "
                    f"manifold={p1!r}, cell={p2!r}"
                )

        logger.warning("Serial connection not established.")
        self._connect_once()
        return PressureReading(datetime.now(), None, None)

    def disconnect(self) -> None:
        """Close the serial connection if open."""

        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("Disconnected MKS.")
