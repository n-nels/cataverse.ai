"""Behavior-frozen gas delivery control for manifold/cell operations.

This module ports legacy gas-delivery sequences with identical branching,
timing, and safety behavior while delegating valve/pressure interactions to
new control/hardware adapters.
"""

from __future__ import annotations

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Any

from src.config_loader import PathsConfig
from src.hardware.pressure import MKSPressure
from src.physics import cell_pressure_from_manifold
from src.datalog.file_io import create_directory, log_actuator_state
from .valves import ValveController


logger = logging.getLogger(__name__)


class GasDelivery:
    """Behavior-frozen gas delivery controller using valve and pressure adapters."""

    def __init__(
        self,
        valves: ValveController,
        pressure: MKSPressure,
        paths: PathsConfig,
        total_volume_l: float,
        temperature_k: float,
        gas_constant: float,
    ) -> None:
        self.valves = valves
        self.pressure = pressure
        self.paths = paths
        self.total_volume_l = total_volume_l
        self.temperature_k = temperature_k
        self.gas_constant = gas_constant

    def read_pressure(self) -> tuple[Any, Any, Any]:
        """Read pressure via controller API.

        Exists so experiment protocols do not reach through to adapter fields.
        """

        return self.pressure.read()

    def pressure_adapter(self) -> MKSPressure:
        """Return pressure adapter via controller API.

        Exists so experiment protocols do not reach through to adapter fields.
        """

        return self.pressure

    def deliver_gas_to_manifold(
        self,
        filename: str | None,
        foldername: str | None,
        id: str,
        target: float,
        openMS: bool = True,
    ) -> tuple[str, float]:
        """Deliver gas to manifold through staged actuator writes and pressure feedback."""

        def pressure_difference(p_mfld_final: Any, p_mfld_initial: Any) -> float:
            global p_mfld_f  # to handle while loop error
            try:
                return abs(p_mfld_final - p_mfld_initial)
            except TypeError:
                logger.info("Overpressure. Evacuating manifold...")
                self.valves.close(id)
                self.valves.write("RoughPump", 1.44)

                dt, p_mfld_f, p_cell = self.pressure.read()
                while isinstance(p_mfld_f, str):
                    dt, p_mfld_f, p_cell = self.pressure.read()
                    time.sleep(1)

                while p_mfld_f > target + (0.05 * target):
                    dt, p_mfld_f, p_cell = self.pressure.read()
                    time.sleep(1)

                self.valves.close("RoughPump")
                time.sleep(20)
                dt, p_mfld_f, p_cell = self.pressure.read()
                logger.info("Manifold pressure is %s", p_mfld_f)
                logger.info(type(p_mfld_f))
                return float(p_mfld_f)

        if filename is not None:
            dir_actLog = os.path.join(self.paths.data_directory, str(foldername))
            path_actLog = os.path.join(dir_actLog, filename + "_actLog.csv")
            create_directory(dir_actLog)
            """[fix] move elsewhere since they create files?
            """

        self.valves.close("RoughPump")
        self.valves.close("TurboPump")
        self.valves.close("irCell")
        if openMS:
            self.valves.open("MassSpec")

        # Read initial value and pressure
        value = self.valves.write("irCell", 1.0)[1]
        step = 0.04
        dither = 0.2
        read_long = 3.0
        read_short = 2.0
        tolerance = 0.01 * target if target >= 1 else 0.01

        act_writes = []
        datetimes = []
        pressures = []
        dithers = []

        dt, p_mfld_f, p_cell = self.pressure.read()
        p_mfld_i = p_mfld_f
        p_mfld_start = p_mfld_f

        while p_mfld_f < (target - tolerance):
            if value < 1.2:
                act_write = float(value) + 0.1
                logger.info("%s write value is %s", id, act_write)
                value = self.valves.write(id, act_write)[1]
                time.sleep(read_short)
                continue
            else:
                dt, p_mfld_f, p_cell = self.pressure.read()
                act_writes.append(act_write)
                datetimes.append(dt)
                pressures.append(p_mfld_f)
                dithers.append(None)

                pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                logger.info(
                    "Manifold pressure is %s ; dP = %s %s",
                    p_mfld_f,
                    pressure_diff,
                    datetime.now(),
                )

                # Decision-making based on resulting pressure
                if (
                    (pressure_diff < tolerance)
                    and (p_mfld_start + (tolerance / 2) > p_mfld_f)
                    and (value <= 1.40)
                ):
                    time.sleep(read_long)
                    dt, p_mfld_i, p_cell = self.pressure.read()

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_i)
                    dithers.append(None)

                    pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)

                    if pressure_diff < tolerance:
                        logger.info("Pressure difference is below tolerance")
                        dt, p_mfld_i, p_cell = self.pressure.read()
                        act_write = float(value) + step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(read_short)
                        continue
                    continue

                elif pressure_diff >= 0.2 * target:
                    act_write = float(value) - step
                    logger.info("%s write value is %s for 0", id, act_write)
                    value = self.valves.write(id, act_write)[1]

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_f)
                    dithers.append(None)

                    time.sleep(read_short)
                    dt, p_mfld_i, p_cell = self.pressure.read()
                    continue

                elif p_mfld_f < 0.5 * target:
                    dither = 0.2

                    while p_mfld_f < 0.5 * target:
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.pressure.read()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        logger.info("%s write value is %s for 1", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.pressure.read()[1])
                        dithers.append(dither)

                        act_write = value - step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(read_long)

                        dt, p_mfld_f, p_cell = self.pressure.read()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        logger.info(
                            "Pressure difference after dithering: %s", pressure_diff
                        )

                        if pressure_diff > target / 4:
                            dither = 0.2

                        if pressure_diff < target / 10:
                            dither *= 2
                            logger.info(
                                "dither duration increased to: %s seconds", dither
                            )

                        if dither > 4:
                            logger.info("dither maximum reached")
                            dither = 0.2
                            act_write = float(value) + step
                            logger.info("%s write value is %s", id, act_write)
                            value = self.valves.write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif (p_mfld_f < target - (0.2 * target)) and (
                    0.125 * target < pressure_diff < 0.5 * target
                ):
                    dt, p_mfld_i, p_cell = self.pressure.read()
                    logger.info("%s write value is %s for 2", id, act_write)

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_i)
                    dithers.append(None)

                    time.sleep(read_short)
                    continue

                elif (p_mfld_start < p_mfld_f < target - (0.2 * target)) and (
                    pressure_diff <= 0.125 * target
                ):
                    dither = 0.2
                    dt, p_mfld_f, p_cell = self.pressure.read()

                    while p_mfld_start < p_mfld_f < target - (0.2 * target):
                        # Dither between two voltage settings
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.pressure.read()
                        if p_mfld_i >= target - (0.2 * target):
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        logger.info("%s write value is %s for 3", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.pressure.read()[1])
                        dithers.append(dither)

                        act_write = value - step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(read_long)
                        dt, p_mfld_f, p_cell = self.pressure.read()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        logger.info(
                            "Pressure difference after dithering: %s", pressure_diff
                        )

                        if (pressure_diff < tolerance * 5) and (
                            p_mfld_f < target - (0.2 * target)
                        ):
                            dither *= 2
                            logger.info(
                                "dither duration increased to: %s seconds", dither
                            )

                        if dither > 4:
                            logger.info("dither maximum reached")
                            dither = 0.2
                            act_write = float(value) + step
                            logger.info("%s write value is %s", id, act_write)
                            value = self.valves.write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif (target - (0.2 * target)) < p_mfld_f <= (target - (0.1 * target)):
                    dither = 0.2
                    dt, p_mfld_f, p_cell = self.pressure.read()

                    while (
                        (target - (0.2 * target))
                        < p_mfld_f
                        <= (target - (0.1 * target))
                    ):
                        # Dither between two voltage settings
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.pressure.read()
                        if p_mfld_i >= target - (0.1 * target):
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        logger.info("%s write value is %s for 4", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.pressure.read()[1])
                        dithers.append(dither)

                        act_write = value - step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(read_short)
                        dt, p_mfld_f, p_cell = self.pressure.read()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        logger.info(
                            "Pressure difference after dithering: %s", pressure_diff
                        )

                        if pressure_diff < (2 * tolerance):
                            dither *= 2  # changed from += 0.25 on 10/26
                            logger.info("dither duration increased to: %s", dither)

                        if dither > 8:
                            logger.info("dither maximum reached")
                            dither = 0.2
                            act_write = float(value) + step
                            logger.info("%s write value is %s", id, act_write)
                            value = self.valves.write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif target - (0.1 * target) < p_mfld_f <= target - (0.05 * target):
                    dither = 0.2
                    act_write = value - step
                    tmp_step = True
                    value = self.valves.write(id, act_write)[1]
                    logger.info("%s write value is %s", id, act_write)
                    dt, p_mfld_f, p_cell = self.pressure.read()

                    while (
                        target - (0.1 * target) < p_mfld_f <= target - (0.05 * target)
                    ):
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.pressure.read()
                        if p_mfld_i > target - (0.05 * target):
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        logger.info("%s write value is %s for 5", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.pressure.read()[1])
                        dithers.append(dither)

                        act_write = value - step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(read_short)

                        dt, p_mfld_f, p_cell = self.pressure.read()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        logger.info(
                            "Pressure difference after dithering: %s", pressure_diff
                        )

                        if (pressure_diff < tolerance) and (
                            p_mfld_f <= target - (0.05 * target)
                        ):
                            dither += 0.2  # Increase dithering duration
                            logger.info("dither duration increased to: %s", dither)

                        if tmp_step and dither > 1:
                            logger.info("dither maximum reached")
                            dither = 0.2
                            act_write = float(value) + step
                            logger.info("%s write value is %s", id, act_write)
                            value = self.valves.write(id, act_write)[1]
                            time.sleep(read_short)

                        if dither > 5:
                            logger.info("dither maximum reached")
                            dither = 0.2
                            act_write = float(value) + step
                            logger.info("%s write value is %s", id, act_write)
                            value = self.valves.write(id, act_write)[1]
                            time.sleep(read_short)
                    continue

                elif target - (0.05 * target) < p_mfld_f < target - tolerance:
                    if pressure_diff > tolerance:
                        act_write = value - step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]

                    dither = 0.2
                    time.sleep(read_short)
                    dt, p_mfld_f, p_cell = self.pressure.read()

                    act_writes.append(act_write)
                    datetimes.append(dt)
                    pressures.append(p_mfld_f)
                    dithers.append(dither)

                    while target - (0.05 * target) < p_mfld_f < target - tolerance:
                        time.sleep(read_short)
                        dt, p_mfld_i, p_cell = self.pressure.read()
                        if p_mfld_i >= target - tolerance:
                            break

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_i)
                        dithers.append(None)

                        act_write = float(value) + step
                        logger.info("%s write value is %s for 6", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(dither)

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(self.pressure.read()[1])
                        dithers.append(dither)

                        act_write = value - step
                        logger.info("%s write value is %s", id, act_write)
                        value = self.valves.write(id, act_write)[1]
                        time.sleep(read_long)

                        dt, p_mfld_f, p_cell = self.pressure.read()

                        act_writes.append(act_write)
                        datetimes.append(dt)
                        pressures.append(p_mfld_f)
                        dithers.append(None)

                        pressure_diff = pressure_difference(p_mfld_f, p_mfld_i)
                        logger.info(
                            "Pressure difference after dithering: %s", pressure_diff
                        )

                        if pressure_diff < tolerance:
                            dither += 0.2  # Increase dithering duration
                            logger.info("dither duration increased to: %s", dither)

                        if dither >= 2:
                            logger.info("dither maximum reached")
                            dither = 0.2
                            act_write = float(value) + step
                            logger.info("%s write value is %s", id, act_write)
                            value = self.valves.write(id, act_write)[1]
                            time.sleep(read_short)
                    continue
                else:
                    time.sleep(read_short)
                    continue

        value = self.valves.write(id, 1)[1]
        logger.info("Shutting gas valve and waiting for pressure equilibration...")
        time.sleep(60)
        dt, p_mfld_f, p_cell = self.pressure.read()
        """maybe deal with O2 faulty valve here???"""

        if p_mfld_f > target + (0.1 * target):
            self.valves.write("RoughPump", 1.44)
            logger.info("Evacuating to achieve target...")
            while p_mfld_f > target + (0.05 * target):
                dt, p_mfld_f, p_cell = self.pressure.read()
                time.sleep(1)
            self.valves.close("RoughPump")
            time.sleep(20)
            dt, p_mfld_f, p_cell = self.pressure.read()

        logger.info(
            "Achieved desired pressure: %s target: %s tolerance: %s",
            p_mfld_f,
            target,
            tolerance,
        )
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
                dithers=dithers,
            )

        return id, p_mfld_f

    def deliver_gas_to_cell(
        self, id: str = "irCell"
    ) -> None:  # [fix] deliver_pretreatment..
        """Admit gas to the IR cell using staged writes and pressure dithering.

        This preserves the legacy pressure-dependent stepping flow used for
        larger gas admissions into the cell volume.
        """

        self.valves.close("MassSpec")

        act_write = 1.0
        value = self.valves.write(id, act_write)[1]
        read_short = 5
        dither = 0.5

        dt, p_mfld_i, p_cell = self.pressure.read()

        while act_write < 1.52:
            step = 0.1 if act_write < 1.4 else 0.04
            act_write = float(value) + step
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, round(act_write, 2))
            time.sleep(5)

        # Measure pressure
        dt, p_mfld_f, p_cell = self.pressure.read()
        pressure_diff = abs(p_mfld_f - p_mfld_i)
        logger.info(
            "Manifold pressure is %s ; dP = %s",
            round(p_mfld_f, 4),
            round(pressure_diff, 4),
        )

        while pressure_diff > 0.02:
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.pressure.read()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.pressure.read()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            logger.info(
                "Manifold pressure is %s ; dP = %s",
                round(p_mfld_f, 4),
                round(pressure_diff, 4),
            )

        while True:
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.pressure.read()
            act_write = float(value) + step
            logger.info("%s write value is %s", id, round(act_write, 2))
            value = self.valves.write(id, act_write)[1]
            time.sleep(dither)

            act_write = value - step
            logger.info("%s write value is %s", id, round(act_write, 2))
            value = self.valves.write(id, act_write)[1]
            time.sleep(read_short)

            dt, p_mfld_f, p_cell = self.pressure.read()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            logger.info(
                "Pressure difference after dithering: %s", round(pressure_diff, 4)
            )

            if pressure_diff < 0.02:
                dither *= 2
                logger.info(
                    "dither duration increased to: %s seconds", round(dither, 2)
                )

            if dither >= 4:
                act_write = float(value) + step
                logger.info("%s write value is %s", id, round(act_write, 2))
                value = self.valves.write(id, act_write)[1]
                dither = 0.5
                break

        while pressure_diff > 0.02:
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.pressure.read()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.pressure.read()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            logger.info(
                "Manifold pressure is %s ; dP = %s",
                round(p_mfld_f, 4),
                round(pressure_diff, 4),
            )

        while True:
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.pressure.read()
            act_write = float(value) + step
            logger.info("%s write value is %s", id, round(act_write, 2))
            value = self.valves.write(id, act_write)[1]
            time.sleep(dither)

            act_write = value - step
            logger.info("%s write value is %s", id, round(act_write, 2))
            value = self.valves.write(id, act_write)[1]
            time.sleep(read_short)

            dt, p_mfld_f, p_cell = self.pressure.read()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            logger.info(
                "Pressure difference after dithering: %s", round(pressure_diff, 4)
            )

            if pressure_diff < 0.02:
                dither *= 2
                logger.info(
                    "dither duration increased to: %s seconds", round(dither, 2)
                )

            if dither >= 4:
                act_write = float(value) + step
                logger.info("%s write value is %s", id, round(act_write, 2))
                value = self.valves.write(id, act_write)[1]
                dither = 0.5
                break

        while act_write < 1.68:
            act_write = float(value) + step
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, round(act_write, 2))
            time.sleep(30)

        value = self.valves.write(id, 5.0)[1]
        logger.info("%s write value is %s", id, round(value, 2))
        time.sleep(30)

    def evacuate_cell(self, id: str) -> str:
        """Evacuate cell-side volume using staged pump-valve opening sequence."""

        self.valves.close("TurboPump")
        self.valves.close("MassSpec")

        if id == "RoughPump":
            id_tmp = False
        else:
            id_tmp = "RoughPump"
            id = id_tmp

        self.valves.open("irCell")

        act_write = 1.0
        value = self.valves.write(id, act_write)[1]
        read_short = 5

        dt, p_mfld_i, p_cell = self.pressure.read()

        while act_write < 1.48:
            step = 0.1 if act_write < 1.4 else 0.04
            act_write = float(value) + step
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)
            time.sleep(5)

        dt, p_mfld_f, p_cell = self.pressure.read()
        pressure_diff = abs(p_mfld_f - p_mfld_i)
        logger.info("Manifold pressure is %s ; dP = %s", p_mfld_f, pressure_diff)

        while pressure_diff > 0.05:
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.pressure.read()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.pressure.read()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            logger.info("Manifold pressure is %s ; dP = %s", p_mfld_f, pressure_diff)

        while act_write < 1.60:
            act_write = float(value) + step
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)
            time.sleep(10)

        value = self.valves.write(id, 5.0)[1]
        logger.info("%s write value is %s", id, value)

        while pressure_diff > 0.0:
            time.sleep(read_short)
            dt, p_mfld_i, p_cell = self.pressure.read()

            time.sleep(read_short)
            dt, p_mfld_f, p_cell = self.pressure.read()
            pressure_diff = abs(p_mfld_f - p_mfld_i)
            logger.info("Manifold pressure is %s ; dP = %s", p_mfld_f, pressure_diff)

        if id_tmp:
            id = "TurboPump"
            time.sleep(5)
            self.valves.open(id)

        return id

    def cell_open_admit(self) -> None:
        """Open ``irCell`` using fixed-time calibration-like voltage schedule."""

        self.valves.close("MassSpec")

        id = "irCell"
        value = 1.0
        i = 0

        act_write = self.valves.write(id, value)[1]

        while act_write < 1.2:
            act_write = float(value) + 0.1
            logger.info("%s write value is %s", id, act_write)
            value = self.valves.write(id, act_write)[1]
            time.sleep(5)

        while act_write < 1.44:
            act_write = float(value) + 0.04
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)
            time.sleep(5)

        while act_write < 1.48:
            act_write = float(value) + 0.04
            logger.info("%s write value is %s", id, act_write)
            value = self.valves.write(id, act_write)[1]
            time.sleep(5)

        while act_write < 1.52:
            act_write = float(value) + 0.04
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)
            time.sleep(15)

        while act_write < 1.56:
            act_write = float(value) + 0.04
            logger.info("%s write value is %s", id, act_write)
            value = self.valves.write(id, act_write)[1]
            time.sleep(3)
            act_write = float(value) - 0.04
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)
            logger.info("i = %s out of 4", i)
            time.sleep(1)
            i += 1
            if i == 5:
                act_write = float(value) + 0.04
                value = self.valves.write(id, act_write)[1]
                time.sleep(20)
                break

        while act_write < 1.6:
            act_write = float(value) + 0.04
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)
            time.sleep(10)

        value = self.valves.write(id, 5.0)[1]
        logger.info("%s write value is %s", id, value)
        time.sleep(20)

    def mass_spec_open_calibration(self) -> None:
        """Open ``MassSpec`` using legacy calibration stepping profile."""

        id = "MassSpec"
        value = 1.0
        i = 0

        act_write = self.valves.write(id, value)[1]

        while act_write < 1.2:
            act_write = float(value) + 0.1
            logger.info("%s write value is %s", id, act_write)
            value = self.valves.write(id, act_write)[1]
            time.sleep(3)

        while act_write < 1.24:
            act_write = float(value) + 0.04
            logger.info("%s write value is %s", id, act_write)
            value = self.valves.write(id, act_write)[1]
            time.sleep(3)

        while act_write < 1.28:
            if i <= 10:  # was 5
                act_write = float(value) + 0.04
                logger.info("%s write value is %s", id, act_write)
                value = self.valves.write(id, act_write)[1]

                time.sleep(0.5)

                act_write = float(value) - 0.04
                value = self.valves.write(id, act_write)[1]
                logger.info("i = %s out of 10", i)

                time.sleep(0.5)
                i += 1

            else:
                act_write = float(value) + 0.04
                value = self.valves.write(id, act_write)[1]
                break

        i = 0

        while act_write < 1.32:
            if i <= 5:
                act_write = float(value) + 0.04
                logger.info("%s write value is %s", id, act_write)
                value = self.valves.write(id, act_write)[1]

                time.sleep(0.25)  # was 0.35

                act_write = float(value) - 0.04
                value = self.valves.write(id, act_write)[1]
                logger.info("i = %s out of 5", i)

                time.sleep(0.5)
                i += 1

            elif i <= 45:  # was 35, currently 35
                act_write = float(value) + 0.04
                logger.info("%s write value is %s", id, act_write)
                value = self.valves.write(id, act_write)[1]

                time.sleep(0.3)  # was 0.5, currently 0.4

                act_write = float(value) - 0.04
                value = self.valves.write(id, act_write)[1]
                logger.info("i = %s out of 35", i)

                time.sleep(0.3)
                i += 1

            elif i > 45 and i <= 65:  # was 35 and 55, currently 35 and 55
                act_write = float(value) + 0.04
                logger.info("%s write value is %s", id, act_write)
                value = self.valves.write(id, act_write)[1]

                time.sleep(1)

                act_write = float(value) - 0.04
                value = self.valves.write(id, act_write)[1]
                logger.info("i = %s out of 55", i)

                time.sleep(0.3)
                i += 1

            else:
                act_write = float(value) + 0.04
                value = self.valves.write(id, act_write)[1]
                wait_time = timedelta(seconds=65)
                logger.info("Wait until: %s", datetime.now() + wait_time)
                time.sleep(35)  # 65
                break

        i = 0

        while act_write < 1.40:
            act_write = float(value) + 0.04
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)

            wait_time = timedelta(seconds=30)
            logger.info("Wait until: %s", datetime.now() + wait_time)
            time.sleep(10)

        while act_write < 1.48:
            act_write = float(value) + 0.04
            value = self.valves.write(id, act_write)[1]
            logger.info("%s write value is %s", id, act_write)

            wait_time = timedelta(seconds=5)
            logger.info("Wait until: %s", datetime.now() + wait_time)
            time.sleep(5)

        value = self.valves.write(id, 5.0)[1]
        logger.info("%s write value is %s", id, value)

        wait_time = timedelta(seconds=300)
        logger.info("Wait until: %s", datetime.now() + wait_time)
        time.sleep(300)

        self.valves.close(id)

    def calc_pressure(self, p1: float, v1: float) -> float:
        """Calculate total pressure in the system using configured total volume."""

        return cell_pressure_from_manifold(p1, v1, self.total_volume_l)
