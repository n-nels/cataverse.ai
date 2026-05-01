"""Behavior-preserving temperature and plug-state control routines.

This module ports the legacy Watlow ramp/hold workflow and Kasa plug state
helpers to the new control layer while preserving timing and branching behavior.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime

from src.core.config_loader import KasaConfig, PathsConfig
from src.datalog.temperature_log_writer import TemperatureLogWriter
from src.hardware.power import KasaPower
from src.hardware.temperature import WatlowTemperature


logger = logging.getLogger(__name__)

DEFAULT_LOG_INTERVAL: int = 10
"""Default interval in seconds between temperature log rows."""


class TemperatureController:
    """Control Watlow temperature ramps and Kasa power states.

    Concurrency
    -----------
    ``watlow`` (and its private helpers ``_ramp_to_target``, ``_cool_to_target``,
    ``_hold_at_target``, ``_hold_at_setpoint``) perform long-running blocking
    loops with Modbus reads/writes to the ``WatlowTemperature`` adapter.  These
    are **not** thread-safe.  ``set_plug_state`` issues HTTP requests to Kasa
    smart plugs via ``KasaPower`` — safe to call from any thread, but the
    underlying ``KasaPower`` adapter is not guarded against concurrent access.
    ``read_temperature`` shares the Modbus connection with ``watlow``; do not
    call concurrently.
    """

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
        log_interval: int = DEFAULT_LOG_INTERVAL,
    ) -> tuple[float, float, float]:
        """Ramp, cool, or hold temperature and log to CSV.

        Parameters
        ----------
        filename:
            Experiment file stem.  ``None`` disables CSV logging.
        foldername:
            Subfolder under the data directory.
        target_temp:
            Desired temperature in °C.
        duration:
            Hold duration in hours.
        rate:
            Ramp rate in °C / min.  ``0`` selects cool or hold branch.
        variac_cmd:
            Whether the variac should remain energised.
        update_interval:
            Seconds between Watlow set-point writes during a ramp.
        log_interval:
            Seconds between CSV log rows (applies to all branches).
        """

        log_writer = TemperatureLogWriter(
            data_directory=self.paths.data_directory,
            filename=filename,
            foldername=foldername,
        )

        current_temp = self.temperature.read_temperature()

        logger.info(
            "Heating to %s°C for %s hours at %s°C/min",
            target_temp,
            duration,
            rate,
        )

        if rate != 0:
            self._ramp_to_target(
                target_temp=target_temp,
                duration=duration,
                rate=rate,
                current_temp=current_temp,
                update_interval=update_interval,
                log_interval=log_interval,
                log_writer=log_writer,
            )
        elif current_temp > target_temp + 5:
            self._cool_to_target(
                target_temp=target_temp,
                duration=duration,
                variac_cmd=variac_cmd,
                current_temp=current_temp,
                log_interval=log_interval,
                log_writer=log_writer,
            )
        else:
            self._hold_at_target(
                target_temp=target_temp,
                duration=duration,
                variac_cmd=variac_cmd,
                log_interval=log_interval,
                log_writer=log_writer,
            )

        return target_temp, rate, duration

    # ------------------------------------------------------------------
    # Private branch methods
    # ------------------------------------------------------------------

    def _ramp_to_target(
        self,
        target_temp: float,
        duration: float,
        rate: float,
        current_temp: float,
        update_interval: int,
        log_interval: int,
        log_writer: TemperatureLogWriter,
    ) -> None:
        """Execute a temperature ramp then hold."""

        setpoints = self._generate_setpoint_list(
            current_temp, target_temp, rate, update_interval
        )

        read_temps: list[float] = []
        time_stamps: list[datetime] = []
        write_temps: list[float] = list(setpoints)

        start_time = datetime.now()
        last_print_time = start_time

        for temp in setpoints[1:]:
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
            if wait > 0:
                time.sleep(wait)

        log_writer.write_ramp_rows(write_temps, read_temps, time_stamps)
        self._hold_at_setpoint(
            setpoint=target_temp,
            duration=duration,
            log_interval=log_interval,
            log_writer=log_writer,
        )

    def _cool_to_target(
        self,
        target_temp: float,
        duration: float,
        variac_cmd: bool,
        current_temp: float,
        log_interval: int,
        log_writer: TemperatureLogWriter,
    ) -> None:
        """Cool to *target_temp* then hold."""

        self.temperature.set_temperature(target_temp)
        state_chg = False

        if not variac_cmd:
            self.set_plug_state(self.kasa.variac_id_vsl, variac_cmd)

        while current_temp > target_temp + 5:
            current_temp = self.temperature.read_temperature()
            if (
                (current_temp <= 1.75 * target_temp + 1.25)
                and (variac_cmd is False)
                and (state_chg is False)
            ):
                self.set_plug_state(self.kasa.variac_id, False)
                state_chg = True

            logger.info(
                "Current temperature: %s C\nTarget temperature: %s C\n",
                current_temp,
                target_temp,
            )

            log_writer.append_hold_row(target_temp, current_temp)
            time.sleep(120)

        self._hold_at_setpoint(
            setpoint=target_temp,
            duration=duration,
            log_interval=log_interval,
            log_writer=log_writer,
        )

    def _hold_at_target(
        self,
        target_temp: float,
        duration: float,
        variac_cmd: bool,
        log_interval: int,
        log_writer: TemperatureLogWriter,
    ) -> None:
        """Set variac state and hold at *target_temp*."""

        if not variac_cmd:
            self.set_plug_state(self.kasa.variac_id_vsl, variac_cmd)
            if self.temperature.read_temperature() <= 1.75 * target_temp + 1.25:
                self.set_plug_state(self.kasa.variac_id, variac_cmd)

        self._hold_at_setpoint(
            setpoint=target_temp,
            duration=duration,
            log_interval=log_interval,
            log_writer=log_writer,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_setpoint_list(
        start_temp: float,
        end_temp: float,
        rate: float,
        interval: int,
    ) -> list[float]:
        """Build a list of intermediate set-point temperatures for a ramp."""

        total_seconds = float(((end_temp - start_temp) / rate) * 60)
        steps = int(total_seconds / interval)
        return [
            round(start_temp + (rate * i * interval / 60.0), 1)
            for i in range(steps + 1)
        ]

    def _hold_at_setpoint(
        self,
        setpoint: float,
        duration: float,
        log_interval: int,
        log_writer: TemperatureLogWriter,
    ) -> None:
        """Hold at *setpoint* for *duration* hours, logging every *log_interval* seconds."""

        hold_seconds = duration * 3600
        end_hold = time.time() + hold_seconds

        logger.info(
            "Hold at %s °C until %s",
            setpoint,
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_hold)),
        )

        while time.time() < end_hold:
            current_temp = self.temperature.read_temperature()
            log_writer.append_hold_row(setpoint, current_temp)

            remaining = end_hold - time.time()
            if remaining < log_interval:
                break

            time.sleep(log_interval)

    def set_plug_state(self, plug_id: str, cmd: bool) -> None:
        """Set a Kasa smart-plug state by plug id."""

        self.power.set_state(plug_id, cmd)

    def set_heating_elements(
        self, chiller: bool, manifold_variac: bool, vessel_variac: bool
    ) -> None:
        """Set chiller and both variac smart-plug states in one call."""

        self.set_plug_state(self.kasa.chiller_id, chiller)
        self.set_plug_state(self.kasa.variac_id, manifold_variac)
        self.set_plug_state(self.kasa.variac_id_vsl, vessel_variac)
