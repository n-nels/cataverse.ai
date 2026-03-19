## device_interface.py

from ..core import get_logger
from ..core.config import extrel_ms_port, watlow_ir_port
from .extrel_mass_spec import ExtrelMassSpec
from .mks_pressure import MKSPressureGauge
from .watlow_controller import WatlowController


logger = get_logger(__name__)


class SerialDevices:
    """Class to control specific devices."""

    def __init__(self):
        """Initializes the DeviceInterface with default settings."""
        self.mks = MKSPressureGauge()
        self.watlow = WatlowController()
        self.extrel = ExtrelMassSpec()

        # Legacy attribute aliases preserved for compatibility.
        self.mks_com = self.mks.mks_com
        self.mks_connection = self.mks.mks_connection
        self.watlow_client = self.watlow.watlow_client
        self.extrel_client = self.extrel.extrel_client

    def _sync_from_components(self) -> None:
        self.mks_com = self.mks.mks_com
        self.mks_connection = self.mks.mks_connection
        self.watlow_client = self.watlow.watlow_client
        self.extrel_client = self.extrel.extrel_client

    def _sync_to_components(self) -> None:
        self.mks.mks_com = self.mks_com
        self.mks.mks_connection = self.mks_connection
        self.watlow.watlow_client = self.watlow_client
        self.extrel.extrel_client = self.extrel_client

    def connect_mks(self):
        self._sync_to_components()
        try:
            self.mks.connect_mks()
        finally:
            self._sync_from_components()

    def connect_extrel(self, port=extrel_ms_port):
        self._sync_to_components()
        try:
            self.extrel.connect_extrel(port=port)
        finally:
            self._sync_from_components()

    def connect_watlow_ir(self, port=watlow_ir_port):
        self._sync_to_components()
        try:
            self.watlow.connect_watlow_ir(port=port)
        finally:
            self._sync_from_components()

    def read_pressure(self, command: str = "p") -> tuple:
        self._sync_to_components()
        try:
            result = self.mks.read_pressure(command=command)
        finally:
            self._sync_from_components()
        return result

    def readTemp_ir(self, address=360, slave_id=1) -> float:
        self._sync_to_components()
        try:
            result = self.watlow.readTemp_ir(address=address, slave_id=slave_id)
        finally:
            self._sync_from_components()
        return result

    def setTemp_ir(self, set_point, address=2160, slave_id=1):
        self._sync_to_components()
        try:
            result = self.watlow.setTemp_ir(set_point, address=address, slave_id=slave_id)
        finally:
            self._sync_from_components()
        return result

    def f2c(self, fahrenheit):
        return self.watlow.f2c(fahrenheit)

    def c2f(self, celcius):
        return self.watlow.c2f(celcius)

    def disconnect(self):
        self._sync_to_components()
        try:
            self.mks.disconnect()
        finally:
            self._sync_from_components()

    def extrel_read(self, address, count=1, unit=1):
        self._sync_to_components()
        try:
            result = self.extrel.extrel_read(address, count=count, unit=unit)
        finally:
            self._sync_from_components()
        return result

    def extrel_write(self, address, value):
        self._sync_to_components()
        try:
            result = self.extrel.extrel_write(address, value)
        finally:
            self._sync_from_components()
        return result

    def decode_ieee754_cdab(self, r0, r1):
        return self.extrel.decode_ieee754_cdab(r0, r1)

    def extrel_stream_test(self, start_address=2, polls=10, poll_interval=1.5, unit=1):
        self._sync_to_components()
        try:
            result = self.extrel.extrel_stream_test(
                start_address=start_address,
                polls=polls,
                poll_interval=poll_interval,
                unit=unit,
            )
        finally:
            self._sync_from_components()
        return result


if __name__ == "__main__":

    device = SerialDevices()

    # device.connect_watlow_ir()
    # # device.setTemp_ir(45)
    # current_temp = device.readTemp_ir()
    # print(f"Current Temperature: {current_temp}°C")

    # device.connect_mks()
    # dt, p_mfld, p_cell = device.read_pressure()
    # print (dt, '\n', p_mfld, '\n', p_cell)
    # if p_mfld == 'Off':
    #     print(type(p_mfld))
    #     device.disconnect()

    # device.connect_extrel()
    # device.extrel_write(address=1, value=2)
    # device.extrel_stream_test()
