## device_interface.py

import struct
import sys
import time
from datetime import datetime

import serial
from pymodbus.client import ModbusSerialClient as ModbusClient


class SerialDevices:
    """Class to control specific devices."""
    def __init__(self):
        """Initializes the DeviceInterface with default settings."""
        self.mks_com = "COM8"
        self.mks_connection = None
        self.watlow_client = None
        self.extrel_client = None

    def connect_mks(self):
        """Establishes a connection to the MKS PDR2000 device."""
        try:
            self.mks_connection = serial.Serial(self.mks_com, baudrate=9600, timeout=2)
            print("Connected to MKS PDR2000 on", self.mks_com)
        except Exception as e:
            print(f"Failed to connect to {self.mks_com}: {e}")

    def connect_extrel(self, port='COM5'):
        """Connect to the Extrel device."""
        self.extrel_client = ModbusClient(port=port, baudrate=9600, parity='N', stopbits=1, bytesize=8, timeout=1)
        print("Connected to Extrel MS on", port)
        if not self.extrel_client.connect():
            print("Unable to connect to Extrel Modbus serial device")
            self.extrel_client = None
    
    def connect_watlow_ir(self, port='COM6'):
            """Connect to a Modbus device."""
            self.watlow_client = ModbusClient(port=port, baudrate=9600, parity='N', stopbits=1, bytesize=8, timeout=1)
            print("Connected to Watlow IR on", port)
            if not self.watlow_client.connect():
                print("Unable to connect to Watlow IR Modbus serial device")
                self.watlow_client = None
    
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

    def readTemp_ir(self, address=360, slave_id=1) -> float:
        """Read temperature from Modbus device.
        address 2172: Read set temperature
        """
        if not self.watlow_client:
            print("Modbus client not connected.")
            return None
        
        result = self.watlow_client.read_holding_registers(address=address, count=2)#, slave=slave_id)
        if result.isError():
            print("Error reading the temperature registers")
            return None
        
        registers = result.registers
        registers_bytes = struct.pack('>HH', registers[1], registers[0])
        temperature = struct.unpack('>f', registers_bytes)
        temperature_c = round(self.f2c(int(temperature[0])), 1)

        if not (0 < temperature_c < 1000):
            result = self.watlow_client.read_holding_registers(address=362, count=2)#, slave=slave_id)
            if result.isError():
                print("Error reading the temperature registers")
                return None
            registers = result.registers
            print(f"Error reading temperature. Error code: {registers[0]}")

            self.setTemp_ir(25)  # Reset to a default temperature

            result = self.watlow_client.read_holding_registers(address=2172, count=2)#, slave=slave_id)
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
        if not self.watlow_client:
            print("Modbus client not connected.")
            return False
        data_bytes = struct.pack('>f', self.c2f(set_point))
        reg_hi, reg_lo = struct.unpack('>HH', data_bytes)
        result = self.watlow_client.write_registers(address=address, values=[reg_lo, reg_hi])#, slave=slave_id)
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

    def extrel_read(self, address, count=1, unit=1):
        """Read from Extrel device."""
        result = self.extrel_client.read_holding_registers(address=address, count=count, device_id=unit)
        if result.isError():
            print("Error reading from Extrel device")
            return None
        registers = result.registers
        return registers

    def extrel_write(self, address, value):
        """Write a value to an Extrel holding register."""
        result = self.extrel_client.write_register(address=address, value=value)
        if result.isError():
            print("Error writing to Extrel device.")
            print(f"Modbus Exception: {result}")
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
                print(f"{i}: read error: {rr}")
            else:
                regs = rr.registers  # 8 regs total
                vals = [
                    self.decode_ieee754_cdab(regs[0], regs[1]),
                    self.decode_ieee754_cdab(regs[2], regs[3]),
                    self.decode_ieee754_cdab(regs[4], regs[5]),
                    self.decode_ieee754_cdab(regs[6], regs[7]),
                ]

                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # milliseconds
                print(
                    f"{ts} | "
                    f"{tags[0]}={vals[0]:.6g} | {tags[1]}={vals[1]:.6g} | "
                    f"{tags[2]}={vals[2]:.6g} | {tags[3]}={vals[3]:.6g}"
                )

            time.sleep(poll_interval)

        return True

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
