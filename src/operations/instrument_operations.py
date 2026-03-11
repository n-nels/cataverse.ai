
"""
This module contains the InstrumentOperations class, which handles the operations of the instruments used in the experiment. It includes methods for delivering gas to the manifold and cell, evacuating the cell, and opening the mass spectrometer.
It also includes methods for logging actuator states and temperatures, and for managing the state of the chiller and variac.
It is designed to work with the ActuatorManager, SerialDevices, and NetworkMessaging classes to control the instruments and communicate with the network.
"""

import csv
import json
import os
import struct
import subprocess
import threading
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta

SRC_PATH = Path(__file__).resolve().parent.parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.core.config import (
    R,
    chiller_id,
    mass,
    metal_load,
    t_mfld,
    v_50tube,
    v_cell,
    v_m1m2m3,
    v_tot,
    variac_id,
    variac_id_vsl,
)
from src.utils.data_logging import create_directory, log_actuator_state, log_temperature


class InstrumentOperations:
    def __init__(self, serial, actuator_control, opus):
        """
        Initialize the InstrumentOperations class, which handles the operations of the instruments used in the experiment.
        """
        self.serial = serial
        self.actuator_control = actuator_control
        self.opus = opus

    def deliver_gas_to_mfld(self, filename, foldername, id, target, openMS=True) -> tuple:
        """
        Deliver gas to the manifold and control the pressure using the actuator control system. Still need a more
        robust overpressure handling system.
        """
        def pressure_difference(p_mfld_final, p_mfld_initial):
            global p_mfld_f # to handle while loop error
            try:
                return abs(p_mfld_final - p_mfld_initial)
            except TypeError:
                print('Overpressure. Evacuating manifold...')
                self.actuator_control.actuator_close(id)
                self.actuator_control.actuator_write('RoughPump', 1.44)

                dt, p_mfld_f, p_cell = self.serial.read_pressure()
                while isinstance(p_mfld_f, str):
                    dt, p_mfld_f, p_cell = self.serial.read_pressure()
                    time.sleep(1)

                while p_mfld_f > target + (0.05*target):
                    dt, p_mfld_f, p_cell = self.serial.read_pressure()
                    time.sleep(1)

                self.actuator_control.actuator_close('RoughPump')
                time.sleep(20)
                dt, p_mfld_f, p_cell = self.serial.read_pressure()
                print('Manifold pressure is ', p_mfld_f)
                print(type(p_mfld_f))
                return float(p_mfld_f)
                
        if filename is not None:
            dir_actLog = 'C://Data//' + foldername
            path_actLog = dir_actLog + '//' + filename + '_actLog.csv'
            create_directory(dir_actLog)

        self.actuator_control.actuator_close('RoughPump')
        self.actuator_control.actuator_close('TurboPump')
        self.actuator_control.actuator_close('irCell')
        if openMS:
            self.actuator_control.actuator_open('MassSpec')

        # Read initial value and pressure
        value = self.actuator_control.actuator_write('irCell', 1.0)[1]
        step = 0.04
        dither = 0.2
        read_long = 3.0
        read_short = 2.0
        tolerance = 0.01*target if target >= 1 else 0.01

        act_writes = []
        datetimes = []
        pressures = []
        dithers = []

        dt, p_mfld_f, p_cell = self.serial.read_pressure()
        p_mfld_i = p_mfld_f
        p_mfld_start = p_mfld_f


        while (p_mfld_f < (target - tolerance)):

            if value < 1.2:
                act_write = float(value) + 0.1
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]
                time.sleep(read_short)
                continue
            else:
                dt, p_mfld_f, p_cell = self.serial.read_pressure()
                act_writes.append(act_write)
                datetimes.append(dt)
                pressures.append(p_mfld_f)
                dithers.append(None)

                pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff, datetime.now())

                # Decision-making based on resulting pressure
                if (pressure_diff < tolerance) and (p_mfld_start + (tolerance/2) > p_mfld_f) and (value <= 1.40):

                    time.sleep(read_long)
                    dt, p_mfld_i, p_cell = self.serial.read_pressure()

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_i)
                    dithers.append(None)

                    pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)

                    if pressure_diff < tolerance:
                        print('Pressure difference is below tolerance')
                        dt, p_mfld_i, p_cell = self.serial.read_pressure()
                        act_write = float(value) + step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(read_short)
                        continue
                    continue

                elif pressure_diff >= 0.2*target:

                    act_write = float(value) - step
                    print(id, 'write value is', act_write, 'at', datetime.now(), 'for 0')
                    value = self.actuator_control.actuator_write(id, act_write)[1]

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_f)
                    dithers.append(None)

                    time.sleep(read_short)
                    dt, p_mfld_i, p_cell = self.serial.read_pressure()
                    continue

                elif (p_mfld_f < 0.5*target):

                    dither = 0.2

                    while (p_mfld_f < 0.5*target):
                    
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.serial.read_pressure()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        print(id, 'write value is', act_write, 'at', datetime.now(), 'for 1')
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.serial.read_pressure()[1])
                        dithers.append(dither)

                        act_write = value - step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(read_long)

                        dt, p_mfld_f, p_cell = self.serial.read_pressure()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        print('Pressure difference after dithering: ', pressure_diff)

                        if (pressure_diff > target/4):
                            dither = 0.2

                        if (pressure_diff < target/10):
                            dither *= 2
                            print('dither duration increased to: ', dither, ' seconds')
                        
                        if dither > 4:
                            print('dither maximum reached')
                            dither = 0.2
                            act_write = float(value) + step
                            print(id, 'write value is', act_write, 'at', datetime.now())
                            value = self.actuator_control.actuator_write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif (p_mfld_f < target - (0.2*target)) and (0.125*target < pressure_diff < 0.5*target):
                    
                    dt, p_mfld_i, p_cell = self.serial.read_pressure()
                    print(id, 'write value is', act_write, 'at', datetime.now(), 'for 2')

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_i)
                    dithers.append(None)

                    time.sleep(read_short)
                    continue

                elif (p_mfld_start < p_mfld_f < target - (0.2*target)) and (pressure_diff <= 0.125*target):

                    dither = 0.2
                    # time.sleep(read_short)
                    dt, p_mfld_f, p_cell = self.serial.read_pressure()

                    while (p_mfld_start < p_mfld_f < target - (0.2*target)):
                        
                        # Dither between two voltage settings
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.serial.read_pressure()
                        if p_mfld_i >= target - (0.2*target):
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        print(id, 'write value is', act_write, 'at', datetime.now(), 'for 3')
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.serial.read_pressure()[1])
                        dithers.append(dither)

                        act_write = value - step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(read_long)
                        dt, p_mfld_f, p_cell = self.serial.read_pressure()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        print('Pressure difference after dithering: ', pressure_diff)

                        if (pressure_diff < tolerance*5) and (p_mfld_f < target - (0.2*target)):
                            dither *= 2
                            print('dither duration increased to: ', dither, ' seconds')
                        
                        if dither > 4:
                            print('dither maximum reached')
                            dither = 0.2
                            act_write = float(value) + step
                            print(id, 'write value is', act_write, 'at', datetime.now())
                            value = self.actuator_control.actuator_write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif ((target - (0.2*target)) < p_mfld_f <= (target - (0.1*target))):
                        
                    dither = 0.2
                    # time.sleep(read_short)
                    dt, p_mfld_f, p_cell = self.serial.read_pressure()

                    while ((target - (0.2*target)) < p_mfld_f <= (target - (0.1*target))):
                        
                        # Dither between two voltage settings
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.serial.read_pressure() 
                        if p_mfld_i >= target - (0.1*target):
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)
                        
                        act_write = float(value) + step
                        print(id, 'write value is', act_write, 'at', datetime.now(), 'for 4')
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.serial.read_pressure()[1])
                        dithers.append(dither)

                        act_write = value - step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(read_short)
                        dt, p_mfld_f, p_cell = self.serial.read_pressure()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        print('Pressure difference after dithering: ', pressure_diff)

                        if pressure_diff < (2*tolerance):
                            dither *= 2  # changed from += 0.25 on 10/26
                            print('dither duration increased to: ', dither)
                        
                        if dither > 8:
                            print('dither maximum reached')
                            dither = 0.2
                            act_write = float(value) + step
                            print(id, 'write value is', act_write, 'at', datetime.now())
                            value = self.actuator_control.actuator_write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif (target - (0.1*target) < p_mfld_f <= target - (0.05*target)):

                    dither = 0.2
                    act_write = value - step
                    tmp_step = True
                    value = self.actuator_control.actuator_write(id, act_write)[1]
                    print(id, 'write value is', act_write, 'at', datetime.now())
                    dt, p_mfld_f, p_cell = self.serial.read_pressure()

                    while (target - (0.1*target) < p_mfld_f <= target - (0.05*target)):
                        
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.serial.read_pressure()
                        if p_mfld_i > target - (0.05*target):
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        print(id, 'write value is', act_write, 'at', datetime.now(), 'for 5')
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.serial.read_pressure()[1])
                        dithers.append(dither)

                        act_write = value - step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(read_short)

                        dt, p_mfld_f, p_cell = self.serial.read_pressure()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        print('Pressure difference after dithering: ', pressure_diff)

                        if (pressure_diff < tolerance) and (p_mfld_f <= target - (0.05*target)):
                            dither += 0.2  # Increase dithering duration
                            print('dither duration increased to: ', dither)

                        if tmp_step and dither > 1:
                            print('dither maximum reached')
                            dither = 0.2
                            act_write = float(value) + step
                            print(id, 'write value is', act_write, 'at', datetime.now())
                            value = self.actuator_control.actuator_write(id, act_write)[1]
                            time.sleep(read_short)
                        
                        if dither > 5:
                            print('dither maximum reached')
                            dither = 0.2
                            act_write = float(value) + step
                            print(id, 'write value is', act_write, 'at', datetime.now())
                            value = self.actuator_control.actuator_write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif (target - (0.05*target) < p_mfld_f < target - tolerance):

                    if pressure_diff > tolerance:
                        act_write = value - step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]

                    dither = 0.2
                    time.sleep(read_short)
                    dt, p_mfld_f, p_cell = self.serial.read_pressure()

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_f)
                    dithers.append(dither)
                
                    while(target - (0.05*target) < p_mfld_f < target - tolerance):
                        
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.serial.read_pressure()
                        if p_mfld_i >= target - tolerance:
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        print(id, 'write value is', act_write, 'at', datetime.now(), 'for 6')
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.serial.read_pressure()[1])
                        dithers.append(dither)

                        act_write = value - step
                        print(id, 'write value is', act_write, 'at', datetime.now())
                        value = self.actuator_control.actuator_write(id, act_write)[1]
                        time.sleep(read_long)

                        dt, p_mfld_f, p_cell = self.serial.read_pressure()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        print('Pressure difference after dithering: ', pressure_diff)

                        if pressure_diff < tolerance:
                            dither += 0.2  # Increase dithering duration
                            print('dither duration increased to: ', dither)
                        
                        if dither >= 2:
                            print('dither maximum reached')
                            dither = 0.2
                            act_write = float(value) + step
                            print(id, 'write value is', act_write, 'at', datetime.now())
                            value = self.actuator_control.actuator_write(id, act_write)[1]
                            time.sleep(read_short)
                    continue
                else: 
                    time.sleep(read_short)
                    continue

        value = self.actuator_control.actuator_write(id, 1)[1]
        print('Shutting gas valve and waiting for pressure equilibration...')
        time.sleep(60)
        dt, p_mfld_f, p_cell = self.serial.read_pressure()
        """maybe deal with O2 faulty valve here???"""

        if p_mfld_f > target + (0.1*target):
            self.actuator_control.actuator_write('RoughPump', 1.44)
            print('Evacuating to achieve target...')
            while p_mfld_f > target + (0.05*target):
                dt, p_mfld_f, p_cell = self.serial.read_pressure()
                time.sleep(1)
            self.actuator_control.actuator_close('RoughPump')
            time.sleep(20)
            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            
        print('Achieved desired pressure: ', p_mfld_f, ' target: ', target, 'tolerance: ', tolerance)
        p_mfld_f = p_mfld_f - p_mfld_start
        if filename is None:
            pass
        else:
            log_actuator_state(
                file_path=path_actLog,
                actuator_id=id,
                act_writes=act_writes,
                pressures=pressures,
                timestamps=datetimes,
                dithers=dithers
            )
        
        return id, p_mfld_f

    def deliver_gas_to_cell(self): # this is for large amounts of gas, pressure dependent

        self.actuator_control.actuator_close('MassSpec')

        id = 'irCell'
        act_write = 1.0
        value = self.actuator_control.actuator_write(id, act_write)[1]
        read_short = 5
        dither = 0.5

        dt, p_mfld_i, p_cell = self.serial.read_pressure()

        while act_write < 1.52:
            step = 0.1 if act_write < 1.4 else 0.04
            act_write = float(value) + step
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(5)

        # Measure pressure
        dt, p_mfld_f, p_cell = self.serial.read_pressure()
        pressure_diff = abs(p_mfld_f - p_mfld_i)
        print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff)

        while (pressure_diff > 0.02):

            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.serial.read_pressure()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff)

        while True:
        
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.serial.read_pressure()
            act_write = float(value) + step
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(dither)

            act_write = value - step
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(read_short)

            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            print('Pressure difference after dithering: ', pressure_diff)

            if (pressure_diff < 0.02):
                dither *= 2
                print('dither duration increased to: ', dither, ' seconds')
            
            if dither >= 4:
                act_write = float(value) + step
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]
                dither = 0.5
                break

        while (pressure_diff > 0.02):

            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.serial.read_pressure()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff)

        while True:
        
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.serial.read_pressure()
            act_write = float(value) + step
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(dither)

            act_write = value - step
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(read_short)

            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            print('Pressure difference after dithering: ', pressure_diff)

            if (pressure_diff < 0.02):
                dither *= 2
                print('dither duration increased to: ', dither, ' seconds')
            
            if dither >= 4:
                act_write = float(value) + step
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]
                dither = 0.5
                break

        while act_write < 1.68:

            act_write = float(value) + step
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(30)

        value = self.actuator_control.actuator_write(id, 5.0)[1]
        print(id, 'write value is', value, 'at', datetime.now())
        time.sleep(30)

    def evacuate_cell(self, id):
        """should check pressure first, if safe for turbo open, open turbo?"""
        self.actuator_control.actuator_close('TurboPump')
        self.actuator_control.actuator_close('MassSpec')

        if id == 'RoughPump':
            id_tmp = False
        else:
            id_tmp = 'RoughPump'
            id = id_tmp

        self.actuator_control.actuator_open('irCell')

        act_write = 1.0
        value = self.actuator_control.actuator_write(id, act_write)[1]
        read_short = 5

        dt, p_mfld_i, p_cell = self.serial.read_pressure()

        while act_write < 1.48:

            step = 0.1 if act_write < 1.4 else 0.04
            act_write = float(value) + step
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(5)

        # Measure pressure
        dt, p_mfld_f, p_cell = self.serial.read_pressure()
        pressure_diff = abs(p_mfld_f - p_mfld_i)
        print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff)

        while (pressure_diff > 0.05):

            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.serial.read_pressure()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff)

        while act_write < 1.60:

            act_write = float(value) + step
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(10)

        value = self.actuator_control.actuator_write(id, 5.0)[1]
        print(id, 'write value is', value, 'at', datetime.now())

        while (pressure_diff > 0.0):

            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.serial.read_pressure()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.serial.read_pressure()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            print('Manifold pressure is ', p_mfld_f, '; dP = ', pressure_diff)
        
        if id_tmp:
            id = 'TurboPump'
            time.sleep(5)
            self.actuator_control.actuator_open(id)
            

        return id

    def cell_open_admit(self):  # this is for IR, fixed time
        
        self.actuator_control.actuator_close('MassSpec')

        id = 'irCell'
        value = 1.0
        i = 0
        
        act_write = self.actuator_control.actuator_write(id, value)[1]
        
        while act_write < 1.2:
            act_write = float(value) + 0.1
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(5)

        while act_write < 1.44:
            act_write = float(value) + 0.04
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(5)

        while act_write < 1.48:
            act_write = float(value) + 0.04
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(5)

        while act_write < 1.52:
            act_write = float(value) + 0.04
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(15)

        while act_write < 1.56:
            act_write = float(value) + 0.04
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(3)
            act_write = float(value) - 0.04
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            print('i =', i, 'out of 4')
            time.sleep(1)
            i += 1
            if i == 5:
                act_write = float(value) + 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1]
                time.sleep(20)
                break

        while act_write < 1.6:
            act_write = float(value) + 0.04
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())
            time.sleep(10)

        value = self.actuator_control.actuator_write(id, 5.0)[1]
        print(id, 'write value is', value, 'at', datetime.now())
        time.sleep(20)

    def MassSpec_open_calibration(self):

        id = 'MassSpec'
        value = 1.0
        i = 0
        
        act_write = self.actuator_control.actuator_write(id, value)[1]
        
        while act_write < 1.2:
            
            act_write = float(value) + 0.1
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(3)

        while act_write < 1.24:
            
            act_write = float(value) + 0.04
            print(id, 'write value is', act_write, 'at', datetime.now())
            value = self.actuator_control.actuator_write(id, act_write)[1]
            time.sleep(3)

        while act_write < 1.28:
            
            if i <= 10:  # was 5
                act_write = float(value) + 0.04
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]

                time.sleep(0.5)

                act_write = float(value) - 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1]
                print('i =', i, 'out of 10')

                time.sleep(0.5)
                i += 1
    
            else:
                act_write = float(value) + 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1]
                break

        i = 0

        while act_write < 1.32:

            if i <= 5:
                act_write = float(value) + 0.04
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]

                time.sleep(0.25) # was 0.35

                act_write = float(value) - 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1] 
                print('i =', i, 'out of 5')

                time.sleep(0.5)
                i += 1

            elif i <= 45:  # was 35, currently 35
                act_write = float(value) + 0.04
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]

                time.sleep(0.3) # was 0.5, currently 0.4

                act_write = float(value) - 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1] 
                print('i =', i, 'out of 35')

                time.sleep(0.3)
                i += 1

            elif i > 45 and i <= 65: # was 35 and 55, currently 35 and 55
                act_write = float(value) + 0.04
                print(id, 'write value is', act_write, 'at', datetime.now())
                value = self.actuator_control.actuator_write(id, act_write)[1]

                time.sleep(1)

                act_write = float(value) - 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1] 
                print('i =', i, 'out of 55')

                time.sleep(0.3)
                i += 1

            else:
                act_write = float(value) + 0.04
                value = self.actuator_control.actuator_write(id, act_write)[1]
                wait_time = timedelta(seconds=65)
                print('Wait until:', datetime.now() + wait_time)
                time.sleep(35) #65
                break

        i = 0

        while act_write < 1.40:

            act_write = float(value) + 0.04
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())

            wait_time = timedelta(seconds=30)
            print('Wait until:', datetime.now() + wait_time)
            time.sleep(10)

        while act_write < 1.48:
            
            act_write = float(value) + 0.04
            value = self.actuator_control.actuator_write(id, act_write)[1]
            print(id, 'write value is', act_write, 'at', datetime.now())

            wait_time = timedelta(seconds=5)
            print('Wait until:', datetime.now() + wait_time)
            time.sleep(5)

        value = self.actuator_control.actuator_write(id, 5.0)[1]
        print(id, 'write value is', value, 'at', datetime.now())

        wait_time = timedelta(seconds=300)
        print('Wait until:', datetime.now() + wait_time)
        time.sleep(300)

        self.actuator_control.actuator_close(id)

    def Watlow(self, filename, foldername, target_temp, duration, rate, variac_cmd, update_interval=2):
        global dir_tempLog, path_tempLog

        def generate_temp_list(start_temp, end_temp, rate, interval):

            total_seconds = float(((end_temp - start_temp) / rate) * 60)
            steps = int(total_seconds / interval)

            return [round(start_temp + (rate * i * interval / 60.0),1) for i in range(steps + 1)]

        def hold_temp(file_path):

            end_hold = time.time() + (duration * 3600)
            print(f"Hold at {target_temp} °C until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_hold))}")
            
            if file_path is None:
                time.sleep(end_hold)
                return
            
            while time.time() < end_hold:
                current_temp = self.serial.readTemp_ir()
                current_time = datetime.now()

                with open(file_path, 'a', newline='') as csv_file:
                    csv_file.write(f"{write_temps[-1]},{current_temp},{current_time}\n")

                if (end_hold - time.time()) < 60:
                    break

                time.sleep(60)
            return

        if filename is not None:
            dir_tempLog = f"C://Data//{foldername}"
            path_tempLog = f"{dir_tempLog}//{filename}_tempLog.csv"
            create_directory(dir_tempLog)

        current_temp = self.serial.readTemp_ir()  # °C
        read_temps = []
        time_stamps = []
        write_temps = []

        print(f"Heating to {target_temp}°C for {duration} hours at {rate}°C/min")

        if rate != 0:
            
            write_temps = generate_temp_list(current_temp, target_temp, rate, update_interval)
            start_time = datetime.now()
            last_print_time = start_time

            for temp in write_temps[1:]:

                now = datetime.now()
                time_stamps.append(now)
                current_temp = self.serial.readTemp_ir()
                read_temps.append(current_temp)

                self.serial.setTemp_ir(temp)

                if (now - last_print_time).total_seconds() >= 30:
                    elapsed_time = (now -start_time).total_seconds()/60
                    print(f"Elapsed Time: {elapsed_time:.2f} min")
                    print(f"Target Temp: {temp} °C")
                    print(f"Current Temp: {current_temp} °C")
                    print(f"Heating to: {target_temp} °C")
                    print(f"Ramp Rate: {rate} °C/min\n")
                    last_print_time = now

                wait = update_interval - (datetime.now() - now).total_seconds()
                
                if wait < 0:
                    continue
                else:
                    time.sleep(wait)

            log_temperature(
                file_path=path_tempLog,
                write_temps=write_temps,
                read_temps=read_temps,
                timestamps=time_stamps
            )
            hold_temp(path_tempLog)

        elif current_temp > target_temp + 5: # for cooling
            self.serial.setTemp_ir(target_temp)
            state_chg = False
            if not variac_cmd: # shut off heating to vessel
                self.kasaPlug_state(variac_id_vsl, variac_cmd)
            while (current_temp > target_temp + 5):
                current_temp = self.serial.readTemp_ir()
                if (current_temp <= 1.75*(target_temp) + 1.25) and (variac_cmd == False) and (state_chg == False):
                    # self.variac_state(False)
                    self.kasaPlug_state(variac_id, False)
                    state_chg = True
                print(f"Current temperature: {current_temp} C\nTarget temperature: {target_temp} C\n")
                time.sleep(120)
            write_temps = [target_temp]
            hold_temp(path_tempLog)

        else:
            if not variac_cmd: # shut off heating to vessel
                self.kasaPlug_state(variac_id_vsl, variac_cmd)
                if self.serial.readTemp_ir() <= 1.75*(target_temp) + 1.25: # shut off variac line
                    self.kasaPlug_state(variac_id, variac_cmd)
            write_temps = [target_temp]
            hold_temp(path_tempLog)

        return target_temp, rate, duration

    def calc_pressure(self, p1, v1):
        """Calculate the total pressure in the system using the ideal gas law.
        Args:
            p1 (float): Pressure in manifold (Torr).
            v1 (float): Volume of manifold (L).
        Returns:
            float: Total pressure in the system (Torr).
        """
        p_tot = p1 * v1 / v_tot
        return p_tot

    def chiller_state(self, cmd):
        """use 'True' for on, 'False' for off"""
        self.run_script('cataverse_venv', 'kasa_smartPlug.py', chiller_id, cmd)

    def variac_state(self, cmd):
        """use 'True' for on, 'False' for off"""
        self.run_script('cataverse_venv', 'kasa_smartPlug.py', variac_id, cmd)
        # self.run_script('cataverse_venv', 'kasa_smartPlug.py', variac_2_id, cmd)

    def kasaPlug_state(self, plug_id, cmd):
        """use 'True' for on, 'False' for off"""
        self.run_script('.venv', 'kasa_smartPlug.py', plug_id, cmd)

    def pressure_log(self, filename: str, stop_event: threading.Event, p_mfld_initial: float, p_cell_initial: float, read_interval: int=5) -> None:
        """Log pressure data to a CSV file.
        Args:
            filename (str): The name of the CSV file to write to.
            stop_event (threading.Event): Event to signal when to stop logging.
            p_mfld_initial (float): Initial pressure in the manifold (m1m2m3+50Tube) (Torr).
            p_cell_initial (float): Initial pressure in the cell (Torr).
            read_interval (int): Time in seconds between readings.
        Returns:
            None
        """
        file_exists = os.path.exists(filename)
        with open(filename, 'a', newline='') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(['timestamp', 'p_mfld', 'p_cell', 'relative_time_s',
                                 'amount_adsorbed_umol/g', 'apparent_conversion', 'apparent_coverage'
                                ])
            t0 = None
            n_initial = (p_mfld_initial * (v_m1m2m3 + v_50tube)) / (R * t_mfld) # mol
            p_initial = ((p_mfld_initial * (v_m1m2m3 + v_50tube)) + (p_cell_initial * v_cell)) / v_tot
            pd_umol_g = metal_load / 10642.0 * 1e6  # umol-Pd/g-material

            try:
                while stop_event is None:
                    try:
                        dt, p_mfld, p_cell = self.serial.read_pressure()
                    except Exception as e:
                        print(f"Error reading pressure: {e}")
                        dt, p_mfld, p_cell = None, None, None
                    
                    # Set initial values if not set
                    if t0 is None and dt is not None:
                        t0 = dt

                    # Calculations
                    if p_mfld is not None:
                        relative_time_s = (dt - t0).total_seconds() if t0 else None
                        n_adsorbed = (p_initial - p_mfld) * v_tot / (R * t_mfld)  # mol
                        amount_adsorbed_umol_g = n_adsorbed * 1e6 / mass
                        n_current = p_mfld * v_tot / (R * t_mfld)
                        apparent_conversion = (n_initial - n_current) / n_initial * 100
                        apparent_coverage = amount_adsorbed_umol_g / pd_umol_g
                    else:
                        amount_adsorbed_umol_g = None
                        apparent_conversion = None
                        apparent_coverage = None
                    
                    writer.writerow([dt, p_mfld, p_cell, relative_time_s,
                                     amount_adsorbed_umol_g, apparent_conversion, apparent_coverage
                                     ])
                    file.flush()
                    time.sleep(read_interval)

                while not stop_event.is_set():
                    try:
                        dt, p_mfld, p_cell = self.serial.read_pressure()
                    except Exception as e:
                        print(f"Error reading pressure: {e}")
                        dt, p_mfld, p_cell = None, None, None

                    # Set initial values if not set
                    if t0 is None and dt is not None:
                        t0 = dt
                    # if p_initial is None and p_mfld is not None:
                    #     p_initial = p_mfld
                    # if n_initial is None and p_initial is not None:
                    #     n_initial = (p_initial * v_tot) / (R * t_mfld)

                    # Calculations
                    if p_mfld is not None and n_initial is not None:
                        relative_time_s = (dt - t0).total_seconds() if t0 else None
                        n_adsorbed = (p_initial - p_mfld) * v_tot / (R * t_mfld)  # mol
                        amount_adsorbed_umol_g = n_adsorbed * 1e6 / mass
                        n_current = p_mfld * v_tot / (R * t_mfld)
                        apparent_conversion = (n_initial - n_current) / n_initial * 100
                        apparent_coverage = amount_adsorbed_umol_g / pd_umol_g
                    else:
                        amount_adsorbed_umol_g = None
                        apparent_conversion = None
                        apparent_coverage = None

                    writer.writerow([
                        dt, p_mfld, p_cell, relative_time_s,
                        amount_adsorbed_umol_g, apparent_conversion, apparent_coverage
                    ])
                    file.flush()
                    time.sleep(read_interval)
            except KeyboardInterrupt:
                print("Pressure logging stopped.")
            finally:
                file.close()

    def OpusVertex80(self, message: dict, timeout_ms: int = 300000, retry_on_timeout: bool = True):
        """Collect spectrum from OPUS Vertex 80 with timeout handling.
        
        Args:
            message: Dictionary containing OPUS command parameters
            timeout_ms: Timeout in milliseconds (default 300000 = 5 minutes)
            retry_on_timeout: If True, reconnect and retry once on timeout
            
        Returns:
            Reply string from OPUS or None on failure
        """
        # Attempt to send message
        msg = self.opus.send_message(message)
        if not msg:
            print("Error: Failed to send message to OPUS")
            return None
            
        print('Collecting spectrum...')
        reply = self.opus.receive_message(timeout_ms=timeout_ms)
        
        # Check if we got a valid response
        if reply:
            print(f"fileid: {reply}")
            return reply
        
        # Timeout or error occurred
        if not retry_on_timeout:
            print("Error: No response from OPUS (timeout)")
            return None
        
        # Timeout recovery: reconnect completely and retry once
        try:
            self.opus.reconnect()
            time.sleep(2)  # Wait for server to recover
            
            # Retry once with fresh socket
            print("Retrying message after reconnect...")
            msg = self.opus.send_message(message)
            if msg:
                reply = self.opus.receive_message(timeout_ms=timeout_ms)
                if reply:
                    print(f"fileid: {reply}")
                    return reply
        except Exception as e:
            print(f"Reconnection or retry failed: {e}")
        
        print("Error: No response from OPUS after timeout and retry")
        return None

    def opusAcquire(self, filename, foldername, repeat, delay, all_fileids, do_bckg, do_fit):
        """To reset all_fileids, do_bckg, or do_fit set equal to True, else False"""

        message = {
            'foldername': foldername,
            'filename': filename,
            'do_bckg': do_bckg,
            'do_fit': do_fit,
            'reset_fileids': all_fileids
            }

        if do_bckg or all_fileids:
            self.OpusVertex80(message)

        message = {
            'foldername': foldername,
            'filename': filename,
            'do_bckg': False,
            'do_fit': do_fit,
            'reset_fileids': False
            }

        # Collect spectra
        j = 0   
        for i in range(len(delay)):
            for k in range(repeat[j]):
                
                now = datetime.now()
                self.OpusVertex80(message)

                print('Collected spectrum ' + str(k+1) + ' of ' + str(repeat[j]) + ' for ' +
                        str(round(float(delay[i])/60, 2)) + ' minute delay')
                
                if i == (len(delay) - 1) and k == (repeat[i] - 1):
                    
                    print('End of OPUS Acquisition')
                    continue
                
                delta = datetime.now() - now
                time_wait = delay[i] - delta.total_seconds()

                if time_wait < 0:
                    continue   

                next_meas = datetime.now() + timedelta(seconds=time_wait)
                print("Next measurement:\n" + str(next_meas) + "\n")
                time.sleep(time_wait)

            j += 1

    def run_script(self, env, script, *args):

        def log(message):
            print("{}: {}".format(datetime.now(), message))

        if env == '.venv':
            python_path = "C:\\Users\\labuser\\CataVerse\\.venv\\Scripts\\python.exe"
        else:
            python_path = "C:\\Program Files\\Python312\\python.exe" # this is not a path

        script_path = f"C:\\Users\\labuser\\CataVerse\\{script}"
        serialized_args = [json.dumps(arg) if isinstance(arg, list) else str(arg) for arg in args]
        # arguments = " ".join(f'"{arg}"' for arg in serialized_args)

        try:
            process = subprocess.Popen(
                        [python_path, script_path] + serialized_args,  # Include the script_path and args in the list
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
                    # Set timeout and capture output and errors
            try:
                output, error = process.communicate(timeout=30)
                print(output.decode())
                # log(f"Output:\n{output.decode()}")
                # log(f"Error:\n{error.decode()}")
                # log(f"Exit Code: {process.returncode}")
            except subprocess.TimeoutExpired:
                process.kill()
                log("Process killed after timeout")
                output, error = process.communicate()
                log(f"Output:\n{output.decode()}")
                log(f"Error:\n{error.decode()}")
        except Exception as e:
            log(f"An error occurred: {e}")
        finally:
            if process.poll() is None:
                process.kill()
                log("Process forcefully killed")

    def temperature_log(self, filename: str, stop_event: threading.Event, read_interval: int = 5) -> None:
        """
        Log temperature data to a CSV file.
        Args:
            filename (str): The name of the CSV file to write to.
            stop_event (threading.Event): Event to signal when to stop logging.
            read_interval (int): Time in seconds between readings.
        Returns:
            None
        """
        with open(filename, 'a', newline='') as file:
            writer = csv.writer(file)
            if not os.path.exists(filename):
                writer.writerow(['timestamp', 'temperature'])
            try:
                while not stop_event.is_set():
                    try:
                        dt = datetime.now()
                        temp = self.serial.readTemp_ir()
                    except Exception as e:
                        print(f"Error reading temperature: {e}")
                        dt, temp = datetime.now(), None
                    writer.writerow([dt, temp])
                    file.flush()
                    time.sleep(read_interval)
            except KeyboardInterrupt:
                print("Temperature logging stopped.")
            finally:
                file.close()

    def extrel_filament(self, cmd: str):
        """cmd: 'on' or 'off'"""
        cmd = 1 if cmd == 'on' else 0
        success = self.serial.extrel_write(address=0, value=cmd) # put address in config file?
        if success:
            print(f"Extrel filament turned {cmd}")
        else:
            print("Failed to change Extrel filament state")

    def extrel_sequence(self, cmd: str):
        """cmd: 'start' or 'stop'"""
        cmd = 2 if cmd == 'start' else 9
        success = self.serial.extrel_write(address=1, value=cmd) # put address in config file?
        if success:
            print("Extrel sequence started" if cmd == 2 else "Extrel sequence stopped")
        else:
            print("Failed to set Extrel sequence")

    def extrel_stream(self, filename: str, stop_event: threading.Event, 
                      start_address=2, poll_interval=1.2, unit=1): # put addresses in config file?
        """
        Reads 4 Paired+IEEE754 values in one contiguous block and logs to CSV.
        
        Args:
            filename (str): Base filename for the data log.
            stop_event (threading.Event): Event to signal when to stop streaming.
            start_address (int): Starting Modbus register address.
            poll_interval (float): Time in seconds between readings.
            unit (int): Modbus unit ID.
        """
        def decode_ieee754_cdab(r0, r1):
            """Decode two Modbus registers (r0, r1) in CDAB order to a float."""
            raw = r1.to_bytes(2, "big") + r0.to_bytes(2, "big")
            return struct.unpack(">f", raw)[0]

        tags = ["V1_I_28", "V1_I_29", "V1_I_44", "V1_I_45"] # put in config file?
        
        file_exists = os.path.exists(filename)
        with open(filename, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(['timestamp'] + tags)
            
            while not stop_event.is_set():
                regs = self.serial.extrel_read(address=start_address, count=8, unit=unit) # tie count to config file?

                if regs is None:
                    print("read error: failed to read from Extrel")
                else:
                    # regs is a list of 8 registers
                    vals = [
                        decode_ieee754_cdab(regs[0], regs[1]),
                        decode_ieee754_cdab(regs[2], regs[3]),
                        decode_ieee754_cdab(regs[4], regs[5]),
                        decode_ieee754_cdab(regs[6], regs[7]),
                    ]

                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # milliseconds                   
                    writer.writerow([ts] + vals)
                    csvfile.flush()

                time.sleep(poll_interval)

        return True


if __name__ == "__main__":
    from src import *

    actuators = ActuatorManager(device_map)
    serial = SerialDevices()
    actuator_control = ActuatorControl(actuators, serial)
    opus = NetworkMessaging()
    iops = InstrumentOperations(serial, actuator_control, opus)

    # temp = iops.serial.readTemp_ir()  # Read initial temperature from IR cell
    # print(temp)

    iops.opusAcquire(filename='test', foldername='_test', repeat=[0], delay=[0],
                all_fileids=True, do_bckg=False, do_fit=False)
    time.sleep(10)
    iops.OpusVertex80(message={'end_experiment': True})

    # iops.evacuate_cell('TurboPump')
    # iops.actuator_control.actuator_close('irCell')
    # iops.actuator_control.actuator_open('MassSpec')
    # iops.deliver_gas_to_mfld(filename=None, foldername=None, id='H2O', target=0.5)
    # iops.deliver_gas_to_cell()
    # iops.actuator_control.actuator_close('irCell')
    # iops.actuator_control.actuator_open('MassSpec')
    # iops.MassSpec_open_calibration()