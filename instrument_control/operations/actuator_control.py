"""
This module provides the ActuatorControl class, which manages the operation of actuators
used in the instrument control system. It includes methods for opening, closing, and
writing values to actuators, as well as safety checks for specific devices like TurboPump
and MassSpec.
"""
import time
import sys
from datetime import datetime

class ActuatorControl:
    def __init__(self, actuators, serial):
        """
        Initializes the ActuatorControl class.
        Args:
            actuators: An instance managing the physical actuators (e.g., valves, mfcs).
            serial: An instance for serial communication with devices (e.g., pressure gauges, watlow).
        """
        self.actuators = actuators
        self.serial = serial

    def actuator_write(self, id: str, value: float)-> tuple[str, float]:
        """
        Writes a value to the specified actuator.
        Args:
            id (str): The identifier of the actuator.
            value (float): The value to write to the actuator.
        Returns:
            Tuple[str, float]: A tuple containing the actuator ID and the rounded value written.
        """
        if value > 5.0:
            self.actuators.set_value(id, 1.0)
            sys.exit("Gas bulb empty")
        self.actuators.set_value(id, value)
        return id, round(float(value), 2) # from decimal import Decimal should be used for rounding

    def actuator_close(self, id: str)-> tuple[str, float]:
        """
        Closes the specified actuator.
        Args:
            id (str): The identifier of the actuator.
        Returns:
            Tuple[str, float]: A tuple containing the actuator ID and the value written.
        """
        value = 1.0
        id, act_write = self.actuator_write(id, value)
        self.print(id, act_write)
        time.sleep(5)
        return id, float(value)

    def actuator_close_all(self, device_map: dict)-> None:
        """
        Closes all actuators.
        Args:
            All id's (dict): The identifier of all actuators.
        """
        print('Closing all actuators...')
        for id in device_map:
            self.actuator_close(id)
        print('All actuators closed.')
        return None

    def actuator_open(self, id: str)-> tuple[str, float]:
        """
        Opens the specified actuator.
        Args:
            id (str): The identifier of the actuator.
        Returns:
            Tuple[str, float]: A tuple containing the actuator ID and the value written.
        """
        safety_checks = {
            'TurboPump': self.safe_turbo_open,
            'MassSpec': self.safe_mass_spec_open,
        }

        if id in safety_checks:
            safety_checks[id]()

        value = 5.0
        id, act_write = self.actuator_write(id, value)
        self.print(id, act_write)
        time.sleep(5)
        return id, float(value)
        
    def safe_turbo_open(self)-> None:
        """
        Ensures the turbo does not open at manifold pressures above 20 mTorr
        """
        dt, p_mfld, p_cell = self.serial.read_pressure()
        if p_mfld > 0.02:
            self.actuator_open('RoughPump')

            while p_mfld > 0.02:
                time.sleep(2)
                dt, p_mfld, p_cell = self.serial.read_pressure()
                print('Manifold pressure is ', p_mfld)

            self.actuator_close('RoughPump')
        else:
            self.actuator_close('RoughPump')
        return None

    def safe_mass_spec_open(self)-> None:
        """
        Ensures the MS is not open above 100 mTorr
        """
        self.actuator_close('irCell')
        dt, p_mfld, p_cell = self.serial.read_pressure()
        if p_cell > 0.1:
            sys.exit("Pressure of cell above limit to open safely")
        return None

    def print(self, id: str, val: float)-> str:
        return print(f"{id} write value is {val} at {datetime.now()}")
