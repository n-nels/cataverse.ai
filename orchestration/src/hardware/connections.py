"""Connection lifecycle manager for hardware-layer device adapters.

This module owns opening/closing low-level communication clients and wiring
them into the new hardware adapter classes.
"""

from __future__ import annotations

import logging

import serial
import zmq
from pymodbus.client import ModbusSerialClient as ModbusClient

from src.core.config_loader import HardwareConfig, SerialDeviceConfig

from .analog_io import AnalogIO
from .errors import HardwareConnectionError
from .mass_spec import ExtrelMassSpec
from .power import KasaPower
from .pressure import MKSPressure
from .spectrometer import OpusSpectrometer
from .temperature import WatlowTemperature


logger = logging.getLogger(__name__)


def _require_modbus_fields(
    config: SerialDeviceConfig, device_name: str
) -> tuple[str, int, int]:
    """Validate and return (parity, stopbits, bytesize) for a Modbus device.

    Raises ``HardwareConnectionError`` if any required field is ``None``.
    """
    missing = []
    if config.parity is None:
        missing.append("parity")
    if config.stopbits is None:
        missing.append("stopbits")
    if config.bytesize is None:
        missing.append("bytesize")
    if missing:
        raise HardwareConnectionError(
            f"{device_name} Modbus config missing required fields: {', '.join(missing)}"
        )
    # At this point the fields are guaranteed non-None
    return config.parity, config.stopbits, config.bytesize  # type: ignore[return-value]


class DeviceManager:
    """Create and own hardware adapter instances and their connections."""

    def __init__(self, config: HardwareConfig) -> None:
        self.config = config

        self._mks_connection: serial.Serial | None = None
        self._watlow_client: ModbusClient | None = None
        self._extrel_client: ModbusClient | None = None
        self._zmq_context: zmq.Context | None = None
        self._zmq_socket: zmq.Socket | None = None

        self.pressure: MKSPressure | None = None
        self.temperature: WatlowTemperature | None = None
        self.mass_spec: ExtrelMassSpec | None = None
        self.analog_io: AnalogIO | None = None
        self.spectrometer: OpusSpectrometer | None = None
        self.power: KasaPower | None = None

    def connect(self) -> None:
        """Open low-level connections and construct all hardware adapters."""

        self._mks_connection = serial.Serial(
            self.config.mks.port,
            baudrate=self.config.mks.baudrate,
            timeout=self.config.mks.timeout_s,
        )

        watlow_parity, watlow_stopbits, watlow_bytesize = _require_modbus_fields(
            self.config.watlow_ir, "Watlow IR"
        )
        self._watlow_client = ModbusClient(
            port=self.config.watlow_ir.port,
            baudrate=self.config.watlow_ir.baudrate,
            parity=watlow_parity,
            stopbits=watlow_stopbits,
            bytesize=watlow_bytesize,
            timeout=self.config.watlow_ir.timeout_s,
        )
        if not self._watlow_client.connect():
            raise HardwareConnectionError(
                "Unable to connect to Watlow IR Modbus serial device"
            )

        extrel_parity, extrel_stopbits, extrel_bytesize = _require_modbus_fields(
            self.config.extrel_ms.serial, "Extrel"
        )
        self._extrel_client = ModbusClient(
            port=self.config.extrel_ms.serial.port,
            baudrate=self.config.extrel_ms.serial.baudrate,
            parity=extrel_parity,
            stopbits=extrel_stopbits,
            bytesize=extrel_bytesize,
            timeout=self.config.extrel_ms.serial.timeout_s,
        )
        if not self._extrel_client.connect():
            raise HardwareConnectionError(
                "Unable to connect to Extrel Modbus serial device"
            )

        self._zmq_context = zmq.Context()
        self._zmq_socket = self._zmq_context.socket(zmq.REQ)
        self._zmq_socket.setsockopt(
            zmq.RCVTIMEO,
            self.config.network.zmq_receive_timeout_ms,
        )

        self.pressure = MKSPressure(self._mks_connection)
        self.temperature = WatlowTemperature(self._watlow_client)
        self.mass_spec = ExtrelMassSpec(self._extrel_client)
        self.analog_io = AnalogIO(self.config.actuator.actuator_map)
        self.spectrometer = OpusSpectrometer(self._zmq_socket)
        self.spectrometer.connect(
            f"tcp://{self.config.network.opus_ip}:{self.config.network.opus_port}"
        )
        self.power = KasaPower(self.config.kasa)

    def disconnect(self) -> None:
        """Close low-level connections created by ``connect()``."""

        if self.pressure is not None:
            self.pressure.disconnect()

        if self._watlow_client is not None:
            try:
                self._watlow_client.close()
            except Exception:
                logger.exception("Error closing Watlow client")
            finally:
                self._watlow_client = None

        if self._extrel_client is not None:
            try:
                self._extrel_client.close()
            except Exception:
                logger.exception("Error closing Extrel client")
            finally:
                self._extrel_client = None

        if self._zmq_socket is not None:
            try:
                self._zmq_socket.setsockopt(zmq.LINGER, 0)
                self._zmq_socket.close()
            except Exception:
                logger.exception("Error closing ZMQ socket")
            finally:
                self._zmq_socket = None

        if self._zmq_context is not None:
            try:
                self._zmq_context.term()
            except Exception:
                logger.exception("Error terminating ZMQ context")
            finally:
                self._zmq_context = None

        self._mks_connection = None
        self.pressure = None
        self.temperature = None
        self.mass_spec = None
        self.analog_io = None
        self.spectrometer = None
        self.power = None
