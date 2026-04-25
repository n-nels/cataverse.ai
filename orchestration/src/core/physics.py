"""Pure gas-law and catalyst-surface calculations for CataVerse.

This module centralizes calculation logic previously implemented inline in
operations and experiments. It has no hardware, threading, network, or file-I/O
dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    n_adsorbed = n_initial_mol - n_equilibrium
    return n_adsorbed * 1e6 / mass_g


def amount_adsorbed_from_pressures(
    p_initial_torr: float,
    source_volume_l: float,
    p_equilibrium_torr: float,
    total_volume_l: float,
    temperature_k: float,
    mass_g: float,
    gas_constant: float = DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL,
) -> float:
    """Return adsorbed amount in µmol/g from initial and equilibrium pressures.

    Convenience wrapper around :func:`amount_adsorbed` that computes the
    initial moles internally, so the caller does not need to call
    :func:`moles_from_pressure` separately with a different volume.

    Parameters
    ----------
    p_initial_torr : float
        Manifold pressure before expansion into the cell.
    source_volume_l : float
        Volume of the gas source (manifold + tube) used for the initial dose.
    p_equilibrium_torr : float
        Pressure after equilibration across the total volume.
    total_volume_l : float
        Total connected volume (manifold + cell + tube + valve).
    temperature_k : float
        Gas temperature in Kelvin.
    mass_g : float
        Catalyst sample mass in grams.
    gas_constant : float
        Gas constant in L·Torr·K⁻¹·mol⁻¹.
    """
    n_initial = moles_from_pressure(
        pressure_torr=p_initial_torr,
        volume_l=source_volume_l,
        temperature_k=temperature_k,
        gas_constant=gas_constant,
    )
    return amount_adsorbed(
        n_initial_mol=n_initial,
        pressure_equilibrium_torr=p_equilibrium_torr,
        total_volume_l=total_volume_l,
        temperature_k=temperature_k,
        mass_g=mass_g,
        gas_constant=gas_constant,
    )


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
