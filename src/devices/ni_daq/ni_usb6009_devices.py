
import nidaqmx
from nidaqmx.constants import AcquisitionType


class NI_USB6009:
    """Class to manage USB communication with NI USB-6009 devices using NI-DAQmx."""
    
    def __init__(self, device_name: str):
        """Initializes the NI_USB6009 with default settings.
        Args:
            device_name: The identifier of the device to initialize.
        """
        self.device_name = device_name
    
    def read_analog_input(self, channel: str) -> float:
        """Reads an analog input from the specified channel.
        Args:
            channel: The channel number to read from, like 'ai0'.
        Returns:
            The analog input value as a float.
        """
        try:
            with nidaqmx.Task() as task:
                task.ai_channels.add_ai_voltage_chan(
                    f"{self.device_name}/{channel}",
                    min_val=10.0,
                    max_val=10.0)
                task.timing.cfg_samp_clk_timing(rate=10000, sample_mode=AcquisitionType.FINITE, samps_per_chan=1)
                
                # Read a single value
                analog_value = task.read()
                # print(f"Read analog input from channel {channel}: {analog_value}")
                return analog_value
        except nidaqmx.DaqError as e:
            print(f"Failed to read analog input from channel {channel}: {e}")
            return 0.0

    def write_analog_output(self, channel: str, value: float) -> bool:
        """Writes an analog output to the specified channel.
        Args:
            channel: The physical channel to write to, like 'ao0'.
            value: The value to write.
        Returns:
            A boolean indicating if the write operation was successful.
        """
        try:
            with nidaqmx.Task() as task:
                task.ao_channels.add_ao_voltage_chan(
                    f"{self.device_name}/{channel}",
                    min_val=0.0,
                    max_val=5.0
                    )
                # Write a single value
                task.write(value)
                # print(f"Wrote analog output to channel {channel}: {value}")
                return True
        except nidaqmx.DaqError as e:
            print(f"Failed to write analog output to channel {channel}: {e}")

class ActuatorManager:
    """Class to manage actuators using NI USB-6009 devices."""
    def __init__(self, device_map):
        self.device_map = device_map

    def set_value(self, id: str, value: float) -> bool:
        """Sets a value based on descriptive ID, referencing the appropriate device and channel.
        Args:
            id: The descriptive ID of the actuator.
            value: The value to set.
        Returns:
            A boolean indicating if the operation was successful.
        """
        device_channel = self.device_map.get(id)
        if not device_channel:
            print(f"No mapping found for ID: {id}")
            return False

        device_name, channel = device_channel
        device = NI_USB6009(device_name)
        return device.write_analog_output(channel, value)

# Mapping descriptive IDs to device and channel
device_map = {
    'v16': ('act1-2', 'ao0'),
    'RoughPump': ('act1-2', 'ao1'),
    'H2': ('act3-4', 'ao0'),
    'H2O': ('act3-4', 'ao1'),
    'MassSpec': ('act5-6', 'ao0'),
    '13CO': ('act5-6', 'ao1'),
    'irCell': ('act7-8', 'ao0'),
    'O2': ('act7-8', 'ao1'),
    'TurboPump': ('act9-10', 'ao0'),
    '': ('act9-10', 'ao1'),
    '': ('act11-12', 'ao0'),
    '': ('act11-12', 'ao1'),
    '': ('act13-14', 'ao0'),
    '': ('act13-14', 'ao1'),
}

if __name__ == "__main__":
    # Example usage
    # from instrument_control.operations.actuator_control import ActuatorControl
    # from instrument_control.devices.serial.serial_devices import SerialDevices

    actuators = ActuatorManager(device_map)
    # serial = SerialDevices()  # replace with your serial class
    # control = ActuatorControl(actuators, serial)

    # success = control.actuator_close_all(device_map)
    # actuators = ActuatorManager(device_map)
    # time.sleep(3)
    success = actuators.set_value('irCell', 5.0)
    # success = actuators.set_value('MassSpec', 1.0)
    # success = actuators.set_value('v16', 5.0)
    # success = actuators.set_value('O2', 1.0)
    # success = actuators.set_value('TurboPump', 1.0)
    # time.sleep(3)
    success = actuators.set_value('RoughPump', 5.0)
    # success = actuators.set_value('irCell', 1.0)
    # time.sleep(5)
    # actuators.set_value('TurboPump', 5.0)
    if success:
        print("Value set successfully.")
    else:
        print("Failed to set value.")




