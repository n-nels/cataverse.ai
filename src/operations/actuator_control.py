"""
This module provides the ActuatorControl class, which manages the operation of actuators
used in the instrument control system. It includes methods for opening, closing, and
writing values to actuators, as well as safety checks for specific devices like TurboPump
and MassSpec.
"""
from typing import Any

import sys
import time
import logging
from datetime import datetime

from src.core.config import (
    actuator_mass_spec_open_max_cell_torr,
    actuator_post_write_sleep_s,
    actuator_turbo_open_max_manifold_torr,
    actuator_turbo_pressure_poll_s,
    actuator_voltage_closed,
    actuator_voltage_max_write,
    actuator_voltage_open,
)


logger = logging.getLogger(__name__)


class ActuatorControl:
    def __init__(self, actuators: Any, serial: Any) -> None:
        """
        Initialize the actuator control facade.

        Args:
            actuators: Device writer providing ``set_value(id, value)``.
            serial: Serial device interface providing ``read_pressure()``.
        """
        self.actuators = actuators
        self.serial = serial

    def actuator_write(self, id: str, value: float) -> tuple[str, float]:
        """
        Write a raw voltage command to a single actuator channel.

        If ``value`` exceeds the configured maximum write voltage, this method first writes
        the configured closed voltage to the same actuator and then exits the process with
        ``"Gas bulb empty"``.

        Args:
            id: Actuator identifier.
            value: Requested actuator voltage.

        Returns:
            Tuple of actuator id and rounded write value.
        """
        if value > actuator_voltage_max_write:
            self.actuators.set_value(id, actuator_voltage_closed)
            sys.exit("Gas bulb empty")
        self.actuators.set_value(id, value)
        return id, round(float(value), 2) # from decimal import Decimal should be used for rounding

    def actuator_close(self, id: str) -> tuple[str, float]:
        """
        Close a single actuator using configured closed voltage.

        Behavior:
        - Calls :meth:`actuator_write` with configured closed voltage.
        - Logs the write event timestamp.
        - Sleeps for configured post-write delay.

        Args:
            id: Actuator identifier.

        Returns:
            Tuple of actuator id and closed voltage value.
        """
        value = actuator_voltage_closed
        id, act_write = self.actuator_write(id, value)
        self.print(id, act_write)
        time.sleep(actuator_post_write_sleep_s)
        return id, float(value)

    def actuator_close_all(self, device_map: dict[str, tuple[str, str]]) -> None:
        """
        Close all actuators listed in ``device_map`` in iteration order.

        For each key in ``device_map``, this calls :meth:`actuator_close`.

        Args:
            device_map: Mapping of actuator ids to (device, channel).
        """
        logger.info('Closing all actuators...')
        for id in device_map:
            self.actuator_close(id)
        logger.info('All actuators closed.')
        return None

    def actuator_open(self, id: str) -> tuple[str, float]:
        """
        Open a single actuator using configured open voltage.

        Safety behavior:
        - For ``TurboPump``, executes :meth:`safe_turbo_open` before opening.
        - For ``MassSpec``, executes :meth:`safe_mass_spec_open` before opening.

        After safety checks, writes configured open voltage, logs write timestamp,
        and sleeps for configured post-write delay.

        Args:
            id: Actuator identifier.

        Returns:
            Tuple of actuator id and open voltage value.
        """
        safety_checks = {
            'TurboPump': self.safe_turbo_open,
            'MassSpec': self.safe_mass_spec_open,
        }

        if id in safety_checks:
            safety_checks[id]()

        value = actuator_voltage_open
        id, act_write = self.actuator_write(id, value)
        self.print(id, act_write)
        time.sleep(actuator_post_write_sleep_s)
        return id, float(value)
        
    def safe_turbo_open(self) -> None:
        """
        Enforce turbo-opening pressure safety sequence.

        Reads manifold pressure and, if above configured turbo-open limit, opens
        ``RoughPump`` and polls pressure at configured interval until at/below limit,
        then closes ``RoughPump``. If already below the limit, closes ``RoughPump``
        via :meth:`actuator_close`.
        """
        dt, p_mfld, p_cell = self.serial.read_pressure()
        if p_mfld > actuator_turbo_open_max_manifold_torr:
            self.actuator_open('RoughPump')

            while p_mfld > actuator_turbo_open_max_manifold_torr:
                time.sleep(actuator_turbo_pressure_poll_s)
                dt, p_mfld, p_cell = self.serial.read_pressure()
                logger.info('Manifold pressure is %s', p_mfld)

            self.actuator_close('RoughPump')
        else:
            self.actuator_close('RoughPump')
        return None

    def safe_mass_spec_open(self) -> None:
        """
        Enforce mass-spec opening pressure safety sequence.

        Closes ``irCell``, reads cell pressure, and exits if cell pressure exceeds the
        configured mass-spec open limit.
        """
        self.actuator_close('irCell')
        dt, p_mfld, p_cell = self.serial.read_pressure()
        if p_cell > actuator_mass_spec_open_max_cell_torr:
            sys.exit("Pressure of cell above limit to open safely")
        return None

    def print(self, id: str, val: float) -> None:
        """Log actuator write id/value with timestamp."""
        logger.info("%s write value is %s at %s", id, val, datetime.now())
