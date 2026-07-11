"""Consolidated hardware test script. Uncomment commands for the component you want to test."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import serial
import zmq
from pymodbus.client import ModbusSerialClient as ModbusClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.control.mass_spec_control import MassSpecController
from src.control.spectrometer_control import SpectrometerController
from src.control.valves import ValveController
from src.core.config_loader import load_config
from src.hardware.analog_io import AnalogIO
from src.hardware.mass_spec import ExtrelMassSpec
from src.hardware.power import KasaPower
from src.hardware.pressure import MKSPressure
from src.hardware.spectrometer import OpusSpectrometer
from src.hardware.temperature import WatlowTemperature


logger = logging.getLogger(__name__)


if __name__ == "__main__":
    config = load_config()

    # --- PRESSURE ---
    mks_cfg = config.hardware.mks
    pressure = MKSPressure(
        serial.Serial(mks_cfg.port, mks_cfg.baudrate, timeout=mks_cfg.timeout_s)
    )

    # --- ANALOG IO / VALVES ---
    analog_io = AnalogIO(config.hardware.actuator.actuator_map)
    valves = ValveController(analog_io, pressure, config.hardware.actuator)

    # --- WATLOW TEMPERATURE ---
    wt = config.hardware.watlow_ir
    watlow_client = ModbusClient(
        port=wt.port,
        baudrate=wt.baudrate,
        parity=wt.parity,
        stopbits=wt.stopbits,
        bytesize=wt.bytesize,
        timeout=wt.timeout_s,
    )
    watlow_client.connect()
    temperature = WatlowTemperature(watlow_client)

    # --- KASA POWER ---
    power = KasaPower(config.hardware.kasa)

    # --- FTIR SPECTROMETER ---
    net = config.hardware.network
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, net.zmq_receive_timeout_ms)
    spectrometer = OpusSpectrometer(sock)
    spectrometer.connect(f"tcp://{net.opus_ip}:{net.opus_port}")

    # --- MASS SPEC ---
    ems = config.hardware.extrel_ms
    extrel_client = ModbusClient(
        port=ems.serial.port,
        baudrate=ems.serial.baudrate,
        parity=ems.serial.parity,
        stopbits=ems.serial.stopbits,
        bytesize=ems.serial.bytesize,
        timeout=ems.serial.timeout_s,
    )
    extrel_client.connect()
    mass_spec = ExtrelMassSpec(extrel_client)

    # --- CONTROLLERS ---
    ftir = SpectrometerController(spectrometer)
    ms = MassSpecController(mass_spec, ems.registers, ems.stream_tags)

    # === PRESSURE ===
    # dt, p_mfld, p_cell = pressure.read()
    # print(f"{dt:%H:%M:%S}  mfld={p_mfld}  cell={p_cell}")

    # === VALVES ===
    # valves.close_all(config.hardware.actuator.actuator_map)
    # valves.write("v16", 1.28)

    # === TEMPERATURE ===
    # t = temperature.read_temperature()
    # success = temperature.set_temperature(25)
    # print(f"Cell temp: {t} C")
    # if success:
    #     print("Success")

    # === KASA PLUGS ===
    # power.set_state(config.hardware.kasa.chiller_id, True)
    # power.set_state(config.hardware.kasa.variac_id, True)
    # power.set_state(config.hardware.kasa.variac_id_vsl, False)

    # === SPECTROMETER ===
    # result = ftir.send_opus_request({"foldername": "_test",
    #                                  "filename": "test",
    #                                  "do_fit": False,
    #                                  "do_bckg": False,
    #                                  "reset_fileids": True
    #                                  })
    # print(f"OPUS result: {result}")

    # === MASS SPEC ===
    # ms.start_sequence()
    # ms.stop_sequence()
    # regs = ms.read_registers(address=1, count=2)
    # print(f"Registers: {regs}")
