## device_interface.py

import serial, struct, time, sys
from pymodbus.client import ModbusSerialClient as ModbusClient
from datetime import datetime


class SerialDevices:
    """Class to control specific devices."""
    def __init__(self):
        """Initializes the DeviceInterface with default settings."""
        self.mks_com = "COM8"
        self.mks_connection = None
        self.modbus_client = None

    def connect_mks(self):
        """Establishes a connection to the MKS PDR2000 device."""
        try:
            self.mks_connection = serial.Serial(self.mks_com, baudrate=9600, timeout=2)
            print("Connected to MKS PDR2000 on", self.mks_com)
        except Exception as e:
            print(f"Failed to connect to {self.mks_com}: {e}")

    def read_pressure(self, command: str = 'p') -> tuple:
        """Reads pressure from the MKS PDR2000 device.
        Args:
            command (str): Command to send to the MKS device. Default is 'p'.
        Returns:
            tuple: A tuple containing the timestamp, pressure in mTorr, and pressure in Torr.
        """

        if self.mks_connection and self.mks_connection.is_open:
            try:
                self.mks_connection.write(command.encode('utf-8'))
                response = self.mks_connection.readline().decode('utf-8').strip()
                # print("response received:", response, datetime.now())
                p1 = response.split(' ')[0]
                p2 = response.split(' ')[-1]
            except Exception as e:
                print(f"Error sending command {command} to {self.mks_com}: {e}")
                try:
                    self.disconnect()
                    time.sleep(2)
                    self.connect_mks()
                    time.sleep(2)
                    self.mks_connection.write(command.encode('utf-8'))
                    response = self.mks_connection.readline().decode('utf-8').strip()
                    p1 = response.split(' ')[0]
                    p2 = response.split(' ')[-1]
                except Exception as e:
                    print(f"Error after reconnecting to {self.mks_com}: {e}")
                    return datetime.now(), None, None
            try:
                return datetime.now(), float(p1), float(p2)
            except ValueError:
                try:
                    return datetime.now(), float(p1), str(p2)
                except ValueError:
                    return datetime.now(), str(p1), str(p2)
        else:
            print("Serial connection not established.")
            self.connect_mks()

    def connect_watlow_ir(self, port='COM6', baudrate=9600):
            """Connect to a Modbus device."""
            self.modbus_client = ModbusClient(port=port, baudrate=baudrate, parity='N', stopbits=1, bytesize=8, timeout=1)
            print("Connected to Watlow IR on", port)
            if not self.modbus_client.connect():
                print("Unable to connect to the Modbus serial device")
                self.modbus_client = None

    def readTemp_ir(self, address=360, slave_id=1) -> float:
        """Read temperature from Modbus device.
        address 2172: Read set temperature
        """
        if not self.modbus_client:
            print("Modbus client not connected.")
            return None
        
        result = self.modbus_client.read_holding_registers(address=address, count=2)#, slave=slave_id)
        if result.isError():
            print("Error reading the temperature registers")
            return None
        
        registers = result.registers
        registers_bytes = struct.pack('>HH', registers[1], registers[0])
        temperature = struct.unpack('>f', registers_bytes)
        temperature_c = round(self.f2c(int(temperature[0])), 1)

        if not (0 < temperature_c < 1000):
            result = self.modbus_client.read_holding_registers(address=362, count=2)#, slave=slave_id)
            if result.isError():
                print("Error reading the temperature registers")
                return None
            registers = result.registers
            print(f"Error reading temperature. Error code: {registers[0]}")

            self.setTemp_ir(25)  # Reset to a default temperature

            result = self.modbus_client.read_holding_registers(address=2172, count=2)#, slave=slave_id)
            if result.isError():
                print("Error reading the temperature registers")
                return None
            registers = result.registers
            registers_bytes = struct.pack('>HH', registers[1], registers[0])
            set_temperature = struct.unpack('>f', registers_bytes)[0]
            set_temperature_c = round(self.f2c(int(set_temperature)), 1)
            print(f"Set temperature is: {set_temperature_c} C")
            sys.exit("Exiting due to temperature read error.")

        # print('Registers:', registers, 'Temperature:', temperature[0], '°F')
        return temperature_c

    def setTemp_ir(self, set_point, address=2160, slave_id=1):
        """Set the target temperature on the Modbus device."""
        if not self.modbus_client:
            print("Modbus client not connected.")
            return False
        data_bytes = struct.pack('>f', self.c2f(set_point))
        reg_hi, reg_lo = struct.unpack('>HH', data_bytes)
        result = self.modbus_client.write_registers(address=address, values=[reg_lo, reg_hi])#, slave=slave_id)
        # print('data bytes:', data_bytes, 'reg_hi:', reg_hi, 'reg_lo:', reg_lo)
        # print('result:', result)
        if result.isError():
            print("Error setting temperature")
            return False
        # print(f"Target temperature set to {set_point}°C")
        return True

    def f2c(self, fahrenheit):
        return (fahrenheit - 32) * 5/9

    def c2f(self, celcius):
        return (celcius * 9/5) + 32

    def disconnect(self):
        if self.mks_connection and self.mks_connection.is_open:
            self.mks_connection.close()
            print("Disconnected MKS.")

if __name__ == "__main__":

    device = SerialDevices()

    device.connect_watlow_ir()
    device.setTemp_ir(45)
    current_temp = device.readTemp_ir()
    print(f"Current Temperature: {current_temp}°C")

    # device.connect_mks()
    # dt, p_mfld, p_cell = device.read_pressure()
    # print (dt, '\n', p_mfld, '\n', p_cell)
    # if p_mfld == 'Off':
    #     print(type(p_mfld))
    # 
    # 
    #     # device.disconnect()