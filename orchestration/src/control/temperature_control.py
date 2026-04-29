"""Behavior-preserving temperature and plug-state control routines.

This module ports the legacy Watlow ramp/hold workflow and Kasa plug state
helpers to the new control layer while preserving timing and branching behavior.
"""

from __future__ import annotations

import os
import time
import logging
from datetime import datetime

from src.core.config_loader import KasaConfig, PathsConfig
from src.hardware.power import KasaPower
from src.hardware.temperature import WatlowTemperature
from src.datalog.file_io import create_directory, log_temperature


logger = logging.getLogger(__name__)

# Legacy global path variables used by watlow() branches.
dir_tempLog: str
path_tempLog: str


class TemperatureController:
    """Control Watlow temperature ramps and Kasa power states."""

    def __init__(
        self,
        temperature: WatlowTemperature,
        power: KasaPower,
        paths: PathsConfig,
        kasa: KasaConfig,
    ) -> None:
        self.temperature = temperature
        self.power = power
        self.paths = paths
        self.kasa = kasa

    def read_temperature(self) -> float:
        """Read temperature via controller API.

        Exists so experiment protocols do not reach through to adapter fields.
        """

        return self.temperature.read_temperature()

    def watlow(
        self,
        filename: str | None,
        foldername: str | None,
        target_temp: float,
        duration: float,
        rate: float,
        variac_cmd: bool,
        update_interval: int = 2,
    ) -> tuple[float, float, float]:
        """Port of legacy Watlow ramp/hold control flow."""

        """
        [fix] This needs to be broken up. Too many concerns based off rate value.
        """

        global dir_tempLog, path_tempLog

        def generate_temp_list(
            start_temp: float,
            end_temp: float,
            rate_value: float,
            interval: int,
        ) -> list[float]:
            total_seconds = float(((end_temp - start_temp) / rate_value) * 60)
            steps = int(total_seconds / interval)
            return [
                round(start_temp + (rate_value * i * interval / 60.0), 1)
                for i in range(steps + 1)
            ]

        def hold_temp(file_path: str | None) -> None:
            end_hold = time.time() + (duration * 3600)
            logger.info(
                "Hold at %s °C until %s",
                target_temp,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_hold)),
            )

            if file_path is None:
                time.sleep(end_hold)
                return

            while time.time() < end_hold:
                current_temp = self.temperature.read_temperature()
                current_time = datetime.now()

                with open(file_path, "a", newline="") as csv_file:
                    csv_file.write(f"{write_temps[-1]},{current_temp},{current_time}\n")

                if (end_hold - time.time()) < 60:
                    break

                time.sleep(60)
            return

        if filename is not None:
            dir_tempLog = os.path.join(self.paths.data_directory, str(foldername))
            path_tempLog = os.path.join(dir_tempLog, f"{filename}_tempLog.csv")
            create_directory(dir_tempLog)
            """[fix] Should these paths be created elsewhere?"""

        current_temp = self.temperature.read_temperature()  # °C
        read_temps = []
        time_stamps = []
        write_temps = []

        logger.info(
            "Heating to %s°C for %s hours at %s°C/min",
            target_temp,
            duration,
            rate,
        )

        if rate != 0:
            write_temps = generate_temp_list(
                current_temp,
                target_temp,
                rate,
                update_interval,
            )
            start_time = datetime.now()
            last_print_time = start_time

            for temp in write_temps[1:]:
                now = datetime.now()
                time_stamps.append(now)
                current_temp = self.temperature.read_temperature()
                read_temps.append(current_temp)

                self.temperature.set_temperature(temp)

                if (now - last_print_time).total_seconds() >= 30:
                    elapsed_time = (now - start_time).total_seconds() / 60
                    logger.info("Elapsed Time: %.2f min", elapsed_time)
                    logger.info("Target Temp: %s °C", temp)
                    logger.info("Current Temp: %s °C", current_temp)
                    logger.info("Heating to: %s °C", target_temp)
                    logger.info("Ramp Rate: %s °C/min\n", rate)
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
                timestamps=time_stamps,
            )
            hold_temp(path_tempLog)

        elif current_temp > target_temp + 5:  # for cooling
            self.temperature.set_temperature(target_temp)
            state_chg = False
            if not variac_cmd:  # shut off heating to vessel
                self.kasa_plug_state(self.kasa.variac_id_vsl, variac_cmd)
            while current_temp > target_temp + 5:
                current_temp = self.temperature.read_temperature()
                if (
                    (current_temp <= 1.75 * (target_temp) + 1.25)
                    and (variac_cmd is False)
                    and (state_chg is False)
                ):
                    self.kasa_plug_state(self.kasa.variac_id, False)
                    state_chg = True
                logger.info(
                    "Current temperature: %s C\nTarget temperature: %s C\n",
                    current_temp,
                    target_temp,
                )
                time.sleep(120)
            write_temps = [target_temp]
            hold_temp(path_tempLog)

        else:
            if not variac_cmd:  # shut off heating to vessel
                self.kasa_plug_state(self.kasa.variac_id_vsl, variac_cmd)
                if (
                    self.temperature.read_temperature() <= 1.75 * (target_temp) + 1.25
                ):  # shut off variac line
                    self.kasa_plug_state(self.kasa.variac_id, variac_cmd)
            write_temps = [target_temp]
            hold_temp(path_tempLog)

        return target_temp, rate, duration

    def chiller_state(self, cmd: bool) -> None:
        """Set chiller smart-plug state by configured device id."""

        self.power.set_state(self.kasa.chiller_id, cmd)

    def variac_state(self, cmd: bool) -> None:
        """Set primary variac smart-plug state by configured device id."""

        self.power.set_state(self.kasa.variac_id, cmd)

    def kasa_plug_state(self, plug_id: str, cmd: bool) -> None:
        """Set arbitrary Kasa smart-plug state by plug id."""

        self.power.set_state(plug_id, cmd)
