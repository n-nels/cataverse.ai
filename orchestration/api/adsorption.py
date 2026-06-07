"""
High-level adsorption experiment API.

Wraps the low-level AdsorptionExperiment building blocks into scientist-readable
operations. Each method is a single conceptual step in a catalysis experiment.

Pressure limits (enforced at runtime before any gas flows):
    Single gas: ~8.3 Torr  (gauge_max × source_m1m2m3 / total)
    Dual gas:   ~[1.6, 6.7] Torr  (gauge_max × [m3/total, source_m1m2/total])
    Exceeding these raises ValueError. See config/system.yaml for gauge_max_pressure_torr.

Usage (from main or notebook):
    from api.adsorption import Adsorption

    ads = Adsorption(inst)
    inst.session.new_experiment()
    ads.clean_surface(evac_temp=450, evac_time=1)
    ads.oxidize_surface(pressure=5.0, temp=450, time=1, evac_temp=450, evac_time=0.5)
    ads.pretreat_adsorbate(adsorbate="H2", pressure=7, temp=250, time=1, evac_temp=250, evac_time=0.5)
    ads.pretreat_adsorbate(adsorbate=["H2O", "O2"], pressure=[1.2, 4.2], temp=650, time=1, evac_temp=650, evac_time=0.5)
    ads.monitor_adsorption(adsorbate="13CO", pressure=0.84, temp=45, repeat=[10, 5, 15, 300])
    ads.finalize(success=True)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.datalog import get_logger
from src.experiments.adsorption import AdsorptionExperiment

if TYPE_CHECKING:
    from src.experiments.setup import Instruments

logger = get_logger(__name__)


class Adsorption:
    """Scientist-facing API for adsorption experiments.

    Composes the atomic methods on AdsorptionExperiment into high-level
    operations that map 1:1 to conceptual experiment steps.
    """

    def __init__(self, inst: Instruments):
        self._ads = AdsorptionExperiment(
            session=inst.session,
            gas_controller=inst.gas,
            temp=inst.temp,
            ftir=inst.ftir,
            ms=inst.ms,
            pressure=inst.devices.pressure,
            temperature=inst.devices.temperature,
        )
        self._inst = inst


    def clean_surface(
        self,
        evac_temp: float,
        evac_time: float,
        ramp_rate: float = 20,
        enable_ms: bool = False,
        chiller: bool = False,
    ) -> None:
        """Evacuate and heat to clean the catalyst surface.

        Args:
            evac_temp: Target temperature during evacuation (°C).
            evac_time: Hold time at target under turbo pump (hours).
            ramp_rate: Heating ramp rate (°C/min). 0 = no ramp (already at temp).
            enable_ms: If True, stream mass-spec data during cleaning.
            chiller: If True, enable chiller during cleaning.
        """
        logger.info("Cleaning surface at %s°C for %s hr", evac_temp, evac_time)
        self._ads.chiller_variac_state(
            chiller_cmd=chiller, variac_cmd=True, variac_vsl_cmd=True
        )
        self._ads.heat_under_evacuation(
            pump_type="RoughPump",
            target_temp=evac_temp,
            hold_time=0.0,
            ramp_rate=ramp_rate,
            enable_ms_stream=enable_ms,
        )
        self._ads.heat_under_evacuation(
            pump_type="TurboPump",
            target_temp=evac_temp,
            hold_time=evac_time,
            ramp_rate=0,
            enable_ms_stream=False,
        )


    def oxidize_surface(
        self,
        pressure: float,
        temp: float,
        time: float,
        evac_temp: float,
        evac_time: float,
        ramp_rate: float = 20,
    ) -> None:
        """Heat cell to temp, dose O2, hold, then evacuate.
        
        Args:
            pressure: O2 target pressure in the total volume (Torr).
            temp: Temperature during oxidation (°C).
            time: Hold time under O2 (hours).
            evac_temp: Temperature during post-oxidation evacuation (°C).
            evac_time: Hold time under turbo pump after oxidation (hours).
            ramp_rate: Heating ramp rate to *temp* (°C/min).
        """
        logger.info(
            "Oxidizing surface: O2 at %.1f Torr, %s°C for %s hr",
            pressure, temp, time,
        )
        self._ads.heat_under_evacuation(
            pump_type="TurboPump",
            target_temp=temp,
            hold_time=0,
            ramp_rate=ramp_rate,
        )
        self._ads.supply_gas_to_mfld(gas="O2", target_pressure=pressure)
        self._ads.deliver_gas_to_cell()
        t_cell, rate, duration = self._ads.heat_cell(temp, time, 0)
        self._ads._log_pretreatment(t_cell, rate, duration, log_gas_calc=True)
        self._ads.heat_under_evacuation(
            pump_type="TurboPump",
            target_temp=evac_temp,
            hold_time=evac_time,
            ramp_rate=0,
        )


    def pretreat_adsorbate(
        self,
        adsorbate: str | list[str],
        pressure: float | list[float],
        temp: float,
        time: float,
        evac_temp: float,
        evac_time: float,
        ramp_rate: float = 20,
    ) -> None:
        """Heat cell to temp, dose pretreatment gas(es), hold, then evacuate.

        Args:
            adsorbate: Gas species to dose. Single string (e.g. "H2") or list
                of two gases for co-adsorption (e.g. ["H2O", "O2"]).
            pressure: Target pressure in the total volume (Torr). Single float
                or list of two floats matching the adsorbate list.
            temp: Temperature during pretreatment (°C).
            time: Hold time under gas (hours).
            evac_temp: Temperature during post-pretreatment evacuation (°C).
            evac_time: Hold time under turbo pump after pretreatment (hours).
            ramp_rate: Heating ramp rate to *temp* (°C/min).
        """
        logger.info(
            "Pretreating with %s at %s Torr, %s°C for %s hr",
            adsorbate, pressure, temp, time,
        )
        self._ads.heat_under_evacuation(
            pump_type="TurboPump",
            target_temp=temp,
            hold_time=0,
            ramp_rate=ramp_rate,
        )
        if isinstance(adsorbate, list):
            self._ads.supply_gases_to_mfld(gas=adsorbate, target_pressure=pressure)
        else:
            self._ads.supply_gas_to_mfld(gas=adsorbate, target_pressure=pressure)

        self._ads.deliver_gas_to_cell()
        t_cell, rate, duration = self._ads.heat_cell(temp, time, 0)
        self._ads._log_pretreatment(t_cell, rate, duration, log_gas_calc=True)
        self._ads.heat_under_evacuation(
            pump_type="TurboPump",
            target_temp=evac_temp,
            hold_time=evac_time,
            ramp_rate=0,
        )


    def monitor_adsorption(
        self,
        adsorbate: str | list[str],
        pressure: float | list[float],
        temp: float,
        repeat: list[int],
        delay: list[int] | None = None,
        all_fileids: bool = True,
        do_bckg: bool = True,
        do_fit: bool = True,
    ) -> None:
        """Cool, dose adsorbate(s), and acquire spectra while monitoring pressure.

        Args:
            adsorbate: Gas species to adsorb. Single string (e.g. "13CO") or
                list of two gases for co-adsorption (e.g. ["13CO", "12CO"]).
            pressure: Target pressure in the total volume (Torr). Single float
                or list of two floats matching the adsorbate list.
            temp: Adsorption temperature (°C).
            repeat: List of repeat counts for spectral acquisition.
            delay: List of delay times (s) between acquisition groups.
            all_fileids: If True, reset OPUS file IDs at start.
            do_bckg: If True, acquire background spectrum first.
            do_fit: If True, run peak fitting after acquisition.
        """
        if delay is None:
            delay = [0] * len(repeat)

        logger.info("Adsorbing %s at %s Torr, %s°C.", adsorbate, pressure, temp)
        self._ads.cool_cell(target_temp=temp, hold_time=0, variac_cmd=False)
        self._ads.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        if isinstance(adsorbate, list):
            self._ads.supply_gases_to_mfld(gas=adsorbate, target_pressure=pressure)
        else:
            self._ads.supply_gas_to_mfld(gas=adsorbate, target_pressure=pressure)
        self._ads.acquire_spectra(
            repeat=repeat,
            delay=delay,
            all_fileids=all_fileids,
            do_bckg=do_bckg,
            do_fit=do_fit,
        )


    def finalize(self, success: bool) -> None:
        """End-of-experiment cleanup: mark success, copy files, notify OPUS."""
        self._ads.finalize(success=success)
