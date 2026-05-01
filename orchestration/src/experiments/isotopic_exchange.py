"""Isotopic exchange calibration experiment protocol using the new architecture layers.

This module provides an isotopic exchange calibration experiment class that coordinates
session metadata, control-layer operations, and hardware access through the
new typed interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import os
import shutil
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path

from src.control.gas_delivery import GasDelivery
from src.control.mass_spec_control import MassSpecController
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.hardware.pressure import MKSPressure
from src.datalog.mass_spec_logger import MassSpecLogger
from src.datalog.pressure_logger import PressureLogger
from src.experiments.session import ExperimentSession
from src.core.physics import cell_pressure_from_manifold


logger = logging.getLogger(__name__)


@dataclass
class IsotopicExchangeCalibration:
    """Orchestrates the isotopic-exchange calibration experiment workflow.

    Coordinates session metadata, gas delivery, temperature control,
    spectrometer operations, and logging while preserving protocol sequencing.
    """

    session: ExperimentSession
    gas_controller: GasDelivery
    temp: TemperatureController
    ftir: SpectrometerController
    mass_spec: MassSpecController
    pressure: MKSPressure

    def __post_init__(self) -> None:
        self.gas: str | tuple[str, str] | None = None
        self.gas_2: str | None = None
        self.p_mfld: float | None = None
        self.p_cell_calc: float | tuple[float, float] | None = None
        self.dt: Any = None
        self.chiller_state: bool | None = None
        self.filename: str | None = None  # for isoX naming convention

    def _act_log_path(self) -> str | None:
        """Build actuator log path from isoX naming convention, or None."""
        if self.filename is None:
            return None
        return str(
            Path(self.session.paths.data_directory)
            / self.foldername
            / f"{self.filename}_actLog.csv"
        )

    def isoX_calib_main(self, xchgTime: list[int], sleepTime: int) -> None:
        """Main function to run the isotopic exchange calibration experiment."""
        for i in range(len(xchgTime)):
            self.filename = self.session.file_name + "_isoX_" + str(i)
            self.foldername = self.session.folder_name

            self.gas_controller.evacuate_cell("TurboPump")
            self.gas_controller.valves.open("MassSpec")
            time.sleep(120)
            self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
                act_log_path=self._act_log_path(),
                id="CO",
                target=1.0,
                openMS=True,
            )
            now = time.time()
            opus_thread = threading.Thread(
                target=self.spec.opus_acquire,
                args=(
                    self.filename,
                    self.foldername,
                    [1],  # repeat
                    [0],  # delay
                    True,  # all fileids
                    False,  # do_bckg
                    True,  # do_fit
                ),
            )
            gas_thread = threading.Thread(target=self.gas_controller.cell_open_admit)
            """gas delivery is 2 min 49 s (best case), open cell is 2 min 11 s"""

            opus_thread.start()
            gas_thread.start()

            gas_thread.join()
            self.gas_controller.valves.close("irCell")
            self.gas_controller.valves.open("TurboPump")
            opus_thread.join()

            wait = (xchgTime[i] * 60) - (time.time() - now)
            logger.info(f"MS open at {datetime.now() + timedelta(seconds=wait)}")
            time.sleep(wait) if wait > 0 else None

            ms_thread = threading.Thread(
                target=self.gas_controller.mass_spec_open_calibration
            )
            ms_thread.start()

            while True:
                dt, p_mfld, p_cell_i = self.gas_controller.read_pressure()
                time.sleep(10)
                dt, p_mfld, p_cell_f = self.gas_controller.read_pressure()
                try:
                    if abs(p_cell_f - p_cell_i) > 0.005:
                        break
                except Exception as e:
                    logger.info(e)

            while True:
                dt, p_mfld, p_cell_i = self.gas_controller.read_pressure()
                time.sleep(6)
                dt, p_mfld, p_cell_f = self.gas_controller.read_pressure()
                logger.info(f"p_cell_f: {p_cell_f}, p_cell_i: {p_cell_i}")
                if abs(p_cell_f - p_cell_i) <= 0.00015:
                    break

            self.spec.opus_acquire(
                filename=self.filename,
                foldername=self.foldername,
                repeat=[1],
                delay=[0],
                all_fileids=False,
                do_bckg=False,
                do_fit=True,
            )
            ms_thread.join()

            if i != len(xchgTime) - 1:
                self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
                    act_log_path=self._act_log_path(),
                    id="13CO",
                    target=1.0,
                    openMS=True,
                )
                self.gas_controller.deliver_gas_to_cell()

            logger.info(
                f"Finished experiment {i + 1} of {len(xchgTime)} with exchange time of {xchgTime[i]}"
            )

            if i == len(xchgTime) - 1:
                continue
            else:
                logger.info(
                    f"Next experiment at {datetime.now() + timedelta(seconds=3600 * sleepTime)}"
                )
                time.sleep(3600 * sleepTime)

    def heat_under_evacuation(
        self,
        pumpType: str,
        targetTemp: int,
        holdTime: float,
        rampRate: int,
        variac_cmd: bool = True,
        expParams: bool = True,
    ) -> None:
        """Heat the cell under evacuation. The pumpType is the type of pump used to evacuate the cell."""
        if pumpType is not None:
            self.gas = self.gas_controller.evacuate_cell(pumpType)
            if holdTime == 0:
                time.sleep(60)
        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            targetTemp,
            holdTime,
            rampRate,
            variac_cmd,
        )
        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()
        if expParams:
            self.session.log_pretreatment(
                gas=self.gas,
                p_gas_meas=(self.p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                rate=rate,
                duration=duration,
            )

    def cool_cell(
        self, targetTemp: int, holdTime: float, variac_cmd: bool, rampRate: int = 0
    ) -> None:
        """Cool the cell to a target temperature. The variac_cmd is used to keep the cell on even at target temperature."""
        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            targetTemp,
            holdTime,
            rampRate,
            variac_cmd,
        )
        while True:
            current_temp = self.temp.read_temperature()
            logger.info(
                f"Current temperature: {current_temp}\nTarget temperature: {t_cell}\n"
            )
            if t_cell + 1 >= current_temp:
                break
            time.sleep(60)
        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()

    def supply_gas_to_mfld(self, gas: str, targetPressure: float) -> None:
        """Supply gas to the manifold. The target pressure corresponds to the pressure in the total volume of the system."""
        self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
            self.session.path_actuator_log,
            id=gas,
            target=targetPressure,
            openMS=True,
        )
        self.p_cell_calc = cell_pressure_from_manifold(
            self.p_mfld,
            self.session.volumes.source_m1m2m3,
            self.session.volumes.total,
        )

    def supply_another_gas_to_mfld(self, gas: str, targetPressure: float) -> None:
        """Supply another gas to the manifold. The gas is delivered to the manifold and the pressure is calculated."""
        self.gas_controller.valves.close("v16")
        self.gas_controller.valves.open("TurboPump")
        time.sleep(120)
        self.gas_2, self.p_mfld_2 = self.gas_controller.deliver_gas_to_manifold(
            self.session.path_actuator_log,
            id=gas,
            target=targetPressure,
            openMS=False,
        )
        self.p_cell_calc = cell_pressure_from_manifold(
            self.p_mfld, self.session.volumes.m3, self.session.volumes.total
        )
        self.p_cell_calc_2 = cell_pressure_from_manifold(
            self.p_mfld_2,
            self.session.volumes.source_m1m2,
            self.session.volumes.total,
        )
        self.gas_controller.valves.open("v16")
        time.sleep(60)

    def acquire_spectra(
        self,
        repeat: list[int],
        delay: list[int],
        all_fileids: bool,
        do_bckg: bool,
        do_fit: bool,
    ) -> None:
        """Acquire spectra from Opus software with threaded acquisition and pressure logging."""
        self.spec.opus_acquire(
            self.session.file_name,
            self.session.folder_name,
            repeat=[0],
            delay=[0],
            all_fileids=all_fileids,
            do_bckg=do_bckg,
            do_fit=do_fit,
        )
        opus_thread = threading.Thread(
            target=self.spec.opus_acquire,
            args=(
                self.session.file_name,
                self.session.folder_name,
                repeat,
                delay,
                False,  # all fileids
                False,  # do_bckg
                do_fit,  # do_fit
            ),
        )
        gas_thread = threading.Thread(target=self.gas_controller.cell_open_admit)

        opus_thread.start()
        gas_thread.start()
        gas_thread.join()
        time.sleep(20)

        dt, p_mfld, p_cell = self.gas_controller.read_pressure()
        if self.gas_2:
            self.session.log_experimental_parameters(
                gas=(self.gas, self.gas_2),
                p_gas_meas=(p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                p_gas_calc=(self.p_cell_calc, self.p_cell_calc_2),
            )
        else:
            self.session.log_experimental_parameters(
                gas=self.gas,
                p_gas_meas=(p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                p_gas_calc=self.p_cell_calc,
            )

        pressure_logger = PressureLogger(
            pressure=self.pressure,
            physics=self.session.volumes,
            path=Path(self.session.path_pressure_log),
            p_mfld_initial=p_mfld,
            p_cell_initial=p_cell,
            mass_g=self.session.sample.mass_g,
            metal_load_wt_percent=self.session.sample.metal_load_wt_percent,
            metal_molar_mass_g_mol=self.session.sample.metal_molar_mass_g_mol,
            temperature_k=self.gas_controller.temperature_k,
            gas_constant=self.gas_controller.gas_constant,
        )
        pressure_logger.start()

        opus_thread.join()
        pressure_logger.stop()

    def introduce_pretreatment_gas_to_cell(
        self,
        targetTemp: int,
        holdTime: float,
        rampRate: int = 0,
        variac_cmd: bool = True,
    ) -> None:
        """Introduce pretreatment gas to the cell and apply temperature ramp/hold."""
        self.gas_controller.deliver_gas_to_cell()
        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            targetTemp,
            holdTime,
            rampRate,
            variac_cmd,
        )
        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()
        if self.gas_2:
            self.session.log_pretreatment(
                gas=(self.gas, self.gas_2),
                p_gas_meas=(self.p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                rate=rate,
                duration=duration,
                p_gas_calc=(self.p_cell_calc, self.p_cell_calc_2),
            )
        else:
            self.session.log_pretreatment(
                gas=self.gas,
                p_gas_meas=(self.p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                rate=rate,
                duration=duration,
                p_gas_calc=self.p_cell_calc,
            )

    def chiller_variac_state(
        self, chiller_cmd: bool, variac_cmd: bool, variac_vsl_cmd: bool
    ) -> None:
        """Set the state of the chiller and variac. The chiller_cmd is used to set the state of the chiller and the variac_cmd is used to set the state of the variac."""
        self.temp.set_plug_state(self.temp.kasa.chiller_id, chiller_cmd)
        self.temp.set_plug_state(self.temp.kasa.variac_id, variac_cmd)
        self.temp.set_plug_state(self.temp.kasa.variac_id_vsl, variac_vsl_cmd)

    def copy_readme(self) -> None:
        """Copy the README.md file to the peakFit folder."""
        path_copy = os.path.join(
            self.session.paths.share_drive_peak_fit_root,
            self.session.folder_name,
            self.session.file_name + "_README.md",
        )
        try:
            shutil.copy(self.session.path_readme, path_copy)
            time.sleep(10)
            self.spec.send_opus_request({"readme": True})
        except IOError as e:
            logger.info(f"An error occurred while copying the file: {e}")

    def massSpec_calibration(self, targets: list) -> None:
        """Run the mass spectrometer calibration experiment."""
        R = self.gas_controller.gas_constant
        t_mfld = self.gas_controller.temperature_k
        v_m3 = self.session.volumes.m3
        v_source_m1m2 = self.session.volumes.source_m1m2
        v_source_m1m2m3 = self.session.volumes.source_m1m2m3
        v_cell = self.session.volumes.cell
        v_tot = self.session.volumes.total
        data_directory = self.session.paths.data_directory
        share_drive_ms_calibrations_root = (
            self.session.paths.share_drive_ms_calibrations_root
        )

        def calculate_number_of_dilutions(target, dilution_factor, initial_moles):
            """Calculate how many dilutions are required to reach the target moles."""
            n_dilutions = 0
            while initial_moles > (target + (target * 0.25)):
                initial_moles *= dilution_factor
                n_dilutions += 1
            return n_dilutions

        filename = f"{self.session.file_name}_msCalib_moles.csv"
        file_path = os.path.join(data_directory, self.session.folder_name, filename)

        dilution_factor = v_m3 / v_source_m1m2m3
        minimum_mfld_moles = 3 * v_source_m1m2m3 / (R * t_mfld)  # 3 Torr minimum
        i = 0

        # collect calibration data
        for target in targets:
            self.gas_controller.valves.open("MassSpec")  # cell closes here
            self.gas_controller.valves.open("TurboPump")
            logger.info(f"Sleep until {datetime.now() + timedelta(seconds=300)}")
            time.sleep(300)

            final_mfld_moles = target / (v_cell / v_tot)
            n_dilutions = calculate_number_of_dilutions(
                final_mfld_moles, dilution_factor, minimum_mfld_moles
            )

            initial_mfld_moles = final_mfld_moles
            for _ in range(n_dilutions):
                initial_mfld_moles /= dilution_factor  # Reverse the effects of dilution

            p_mfld_calc = (initial_mfld_moles * R * t_mfld) / v_source_m1m2m3
            id, p_mfld = self.gas_controller.deliver_gas_to_manifold(
                act_log_path=None, id="13CO", target=p_mfld_calc
            )
            moles = p_mfld * v_source_m1m2m3 / (R * t_mfld)

            j = 0
            while True:
                moles = moles * dilution_factor
                self.gas_controller.valves.close("v16")
                time.sleep(5)
                self.gas_controller.valves.open("TurboPump")
                logger.info(f"Sleep until {datetime.now() + timedelta(seconds=300)}")
                time.sleep(300)
                self.gas_controller.valves.close("TurboPump")
                time.sleep(5)
                self.gas_controller.valves.open("v16")
                time.sleep(60)

                expected_final_dilution = moles * dilution_factor
                expected_final_moles = expected_final_dilution * v_cell / v_tot
                if abs(expected_final_moles - target) < target * 0.25:
                    logger.info(
                        f"Target mole value of {expected_final_moles:.4e} reached. Target moles is {target}. Execute final dilution."
                    )
                    break
                logger.info(f"Dilution {j + 1}:")
                logger.info(
                    f"Expected calibration moles is {expected_final_moles:.4e}. Target moles is {target} Diluting again..."
                )
                j += 1

            # final dilution
            self.gas_controller.valves.close("v16")
            time.sleep(5)
            self.gas_controller.valves.open("TurboPump")
            logger.info(f"Sleep until {datetime.now() + timedelta(seconds=300)}")
            time.sleep(300)
            self.gas_controller.valves.close("TurboPump")
            id, p_mfld = self.gas_controller.deliver_gas_to_manifold(
                act_log_path=None,
                id="CO",
                target=v_source_m1m2m3 / v_source_m1m2,
            )
            self.gas_controller.valves.open("v16")
            moles = moles * dilution_factor
            time.sleep(60)

            # introduce gas to cell
            self.gas_controller.cell_open_admit()
            self.gas_controller.valves.close("irCell")
            time.sleep(5)
            self.gas_controller.valves.open("RoughPump")
            moles = moles * v_cell / v_tot
            logger.info(f"final moles = {moles:.4e}. Target moles = {target:.2e}")

            if os.path.exists(file_path):
                with open(file_path, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    name = f"{self.session.file_name}_msCalib_{i}.csv"
                    writer.writerow([name, timestamp, moles])
            else:
                with open(file_path, mode="w", newline="") as file:
                    writer = csv.writer(file)
                    headers = ["Filename", "Timestamp", "13CO_Moles"]
                    writer.writerow(headers)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    name = f"{self.session.file_name}_msCalib_{i}.csv"
                    writer.writerow([name, timestamp, moles])

            self.gas_controller.mass_spec_open_calibration()
            logger.info(f"Finished calibration {i + 1} of {len(targets)}")
            i += 1

        i = 0
        for _ in range(2):
            self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
                act_log_path=None, id="CO", target=1.0
            )
            self.gas_controller.deliver_gas_to_cell()
            self.gas_controller.valves.close("irCell")
            self.gas_controller.valves.open("TurboPump")
            time.sleep(10)
            moles = 0

            with open(file_path, mode="a", newline="") as file:
                writer = csv.writer(file)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                name = f"{self.session.file_name}_msCalib_{i}.csv"
                writer.writerow([name, timestamp, moles])

            self.gas_controller.mass_spec_open_calibration()
            logger.info(f"Finished calibration {i + 1} of {len(range(2))}")
            i += 1

        path_copy = os.path.join(
            share_drive_ms_calibrations_root,
            self.session.folder_name,
            filename,
        )
        try:
            shutil.copy(file_path, path_copy)
        except IOError as e:
            logger.info(f"An error occurred while copying the file: {e}")
