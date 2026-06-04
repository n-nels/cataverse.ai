"""Pure gas-law and catalyst-surface calculations for cataverse platform."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple


DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL = 62.363577
DEFAULT_TEMPERATURE_K = 298.0
AVOGADRO_NUMBER_PER_MOL = 6.023e23


@dataclass(frozen=True)
class SystemVolumes:
    """Calibrated system volumes in liters."""

    vessel: float
    valve: float
    cell: float
    manifold_m1m2: float
    manifold_m1m2m3: float
    tube_50ml: float
    flask: float
    gauge_max_pressure_torr: float

    @property
    def m3(self) -> float:
        """Volume of manifold section m3 [L]."""

        return self.manifold_m1m2m3 - self.manifold_m1m2 - self.valve

    @property
    def source_m1m2(self) -> float:
        """Source volume for gas delivery via m1+m2 manifold sections [L]."""

        return self.manifold_m1m2 + self.tube_50ml

    @property
    def source_m1m2m3(self) -> float:
        """Source volume for gas delivery via full manifold [L]."""

        return self.manifold_m1m2m3 + self.tube_50ml

    @property
    def total(self) -> float:
        """Total connected experiment volume [L]."""

        return self.manifold_m1m2m3 + self.cell + self.valve + self.tube_50ml

    @property
    def max_target_pressure(self) -> float:
        """Max allowable target pressure (Torr) for single-gas delivery.

        Derived from gauge limit × (source_m1m2m3 / total).
        """
        return self.gauge_max_pressure_torr * self.source_m1m2m3 / self.total

    @property
    def max_target_pressure_dual(self) -> tuple[float, float]:
        """Max allowable target pressures (Torr) for two-gas co-adsorption.

        Returns (limit_gas_1, limit_gas_2) derived from gauge limit ×
        (m3 / total) and gauge limit × (source_m1m2 / total) respectively.
        """
        return (
            self.gauge_max_pressure_torr * self.m3 / self.total,
            self.gauge_max_pressure_torr * self.source_m1m2 / self.total,
        )


class PressureMetrics(NamedTuple):
    """Derived metrics computed per pressure-logger tick."""

    relative_time_s: float | None
    amount_adsorbed_umol_per_g: float
    apparent_conversion: float
    apparent_coverage: float


def moles_from_pressure(
    pressure_torr: float,
    volume_l: float,
    temperature_k: float,
    gas_constant: float = DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL,
) -> float:
    """Return moles from ideal gas law using Torr and liters."""

    return (pressure_torr * volume_l) / (gas_constant * temperature_k)


def cell_pressure_from_manifold(
    pressure_manifold_torr: float,
    source_volume_l: float,
    total_volume_l: float,
) -> float:
    """Return equilibrium pressure after expansion to total volume."""

    return pressure_manifold_torr * source_volume_l / total_volume_l


def amount_adsorbed(
    n_initial_mol: float,
    pressure_equilibrium_torr: float,
    total_volume_l: float,
    temperature_k: float,
    mass_g: float,
    gas_constant: float = DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL,
) -> float:
    """Return adsorbed amount in µmol/g from initial moles and equilibrium pressure."""

    n_equilibrium = moles_from_pressure(
        pressure_torr=pressure_equilibrium_torr,
        volume_l=total_volume_l,
        temperature_k=temperature_k,
        gas_constant=gas_constant,
    )
    n_adsorbed = n_initial_mol - n_equilibrium # need to account for initial adsorption
    return n_adsorbed * 1e6 / mass_g


def metal_surface_density(
    metal_load_wt_percent: float,
    molar_mass_g_mol: float,
    support_surface_area_m2_g: float,
) -> float:
    """Return metal atom surface density in nm^-2.

    Formula:
      (metal_load / 100) * (1 / molar_mass) * (6.023e23) * (1 / support_sa) * (1e-9**2)
    """

    return (
        (metal_load_wt_percent / 100)
        * (1 / molar_mass_g_mol)
        * AVOGADRO_NUMBER_PER_MOL
        * (1 / support_surface_area_m2_g)
        * (1e-9**2)
    )


def compute_pressure_metrics(
    p_mfld: float,
    dt: datetime,
    t0: datetime | None,
    p_mfld_initial: float,
    p_cell_initial: float,
    source_volume_l: float,
    total_volume_l: float,
    cell_volume_l: float,
    mass_g: float,
    metal_load_wt_percent: float,
    metal_molar_mass_g_mol: float,
    temperature_k: float,
    gas_constant: float = DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL,
) -> PressureMetrics:
    """Compute per-tick pressure-derived metrics for the pressure logger.

    Pure function — no I/O, no threading.  Unit-testable in isolation.
    """

    # Moles dosed from source (manifold) before expansion into cell
    n_dosed = (p_mfld_initial * source_volume_l) / (gas_constant * temperature_k)

    # Expected equilibrium pressure if nothing adsorbs (mixing source + cell)
    p_initial = (
        (p_mfld_initial * source_volume_l) + (p_cell_initial * cell_volume_l)
    ) / total_volume_l

    # Total moles in the combined system after mixing (source + cell)
    n_initial = (p_initial * total_volume_l) / (gas_constant * temperature_k)

    # Amount adsorbed = (total system moles) - (moles remaining in gas phase now)
    amount_adsorbed_umol_g = amount_adsorbed(
        n_initial_mol=n_initial,
        pressure_equilibrium_torr=p_mfld,
        total_volume_l=total_volume_l,
        temperature_k=temperature_k,
        mass_g=mass_g,
        gas_constant=gas_constant,
    )

    # Moles currently in gas phase at measured pressure
    n_gas_current = p_mfld * total_volume_l / (gas_constant * temperature_k)

    # Fraction of dosed gas consumed (%)
    apparent_conversion = (n_dosed - n_gas_current) / n_dosed * 100

    # Coverage: adsorbed amount relative to total metal sites
    pd_umol_g = (metal_load_wt_percent / 100) * (1 / metal_molar_mass_g_mol) * 1e6
    apparent_coverage = amount_adsorbed_umol_g / pd_umol_g

    relative_time_s = (dt - t0).total_seconds() if t0 is not None else None

    return PressureMetrics(
        relative_time_s=relative_time_s,
        amount_adsorbed_umol_per_g=amount_adsorbed_umol_g,
        apparent_conversion=apparent_conversion,
        apparent_coverage=apparent_coverage,
    )
