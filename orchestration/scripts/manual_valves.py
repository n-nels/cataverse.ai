from __future__ import annotations

import logging
import sys
from pathlib import Path
from time import time

import serial

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.control.valves import ValveController
from src.core.config_loader import load_config
from src.hardware.analog_io import AnalogIO
from src.hardware.pressure import MKSPressure


if __name__ == "__main__":
    
    config = load_config()
    analog_io = AnalogIO(config.hardware.actuator.actuator_map)
    mks = config.hardware.mks

    pressure = MKSPressure(
        serial.Serial(mks.port, mks.baudrate, timeout=mks.timeout_s)
    )

    valves = ValveController(analog_io, pressure, config.hardware.actuator)
    # valves = ValveController(analog_io, config.hardware.actuator)

    # success = valves.close_all(config.hardware.actuator.actuator_map)

    # success = valves.write("v16", 5.0)

    # success = valves.write("irCell", 5.0)

    # success = valves.write("MassSpec", 5.0)

    # success = valves.write("RoughPump", 1.0)

    success = valves.write("TurboPump", 5.0)

    if success:
        print("Success")

    dt, p_mfld, p_cell = pressure.read()
    print(f"{dt:%H:%M:%S}  mfld={p_mfld}  cell={p_cell}")
