"""Unit tests for pure calculations in ``src.physics``."""

from __future__ import annotations

import pytest

from src.core.physics import (
    DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL,
    SystemVolumes,
    amount_adsorbed,
    cell_pressure_from_manifold,
    metal_surface_density,
    moles_from_pressure,
)


def test_system_volumes_properties_match_legacy_config_values() -> None:
    volumes = SystemVolumes(
        vessel=0.0119913,
        valve=0.000152,
        cell=0.03381,
        manifold_m1m2=0.078862,
        manifold_m1m2m3=0.11116,
        tube_50ml=0.05643,
        flask=1.004,
    )

    # Legacy equivalents in core.config:
    # v_m3 = v_m1m2m3 - v_m1m2 - v_valve
    # v_tot = v_m1m2m3 + v_cell + v_valve + v_50tube
    assert volumes.m3 == pytest.approx(0.032145999999999994)
    assert volumes.total == pytest.approx(0.201552)


def test_moles_from_pressure_known_value() -> None:
    # Hand-calculated from ideal gas law n = pV / RT
    expected = (10.0 * 0.2) / (DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL * 298.0)
    actual = moles_from_pressure(pressure_torr=10.0, volume_l=0.2, temperature_k=298.0)

    assert actual == pytest.approx(expected)


def test_moles_from_pressure_zero_pressure_returns_zero() -> None:
    assert moles_from_pressure(pressure_torr=0.0, volume_l=0.2, temperature_k=298.0) == 0.0


def test_moles_from_pressure_zero_temperature_raises_zero_division_error() -> None:
    with pytest.raises(ZeroDivisionError):
        moles_from_pressure(pressure_torr=1.0, volume_l=0.2, temperature_k=0.0)


def test_cell_pressure_from_manifold_known_value() -> None:
    # Hand-calculated p2 = p1 * v_source / v_total
    expected = 2.0 * 0.11116 / 0.201552
    actual = cell_pressure_from_manifold(
        pressure_manifold_torr=2.0,
        source_volume_l=0.11116,
        total_volume_l=0.201552,
    )

    assert actual == pytest.approx(expected)


def test_cell_pressure_from_manifold_zero_total_volume_raises_zero_division_error() -> None:
    with pytest.raises(ZeroDivisionError):
        cell_pressure_from_manifold(
            pressure_manifold_torr=2.0,
            source_volume_l=0.11116,
            total_volume_l=0.0,
        )


def test_amount_adsorbed_known_value() -> None:
    # Hand-calculated using legacy equations from instrument_operations.pressure_log:
    # n = pV/RT and amount_adsorbed_umol_g = (n_initial - n_current) * 1e6 / mass
    n_initial = 1.5e-5
    p_eq = 3.2
    total_volume = 0.201552
    temp_k = 298.0
    mass_g = 0.0164

    n_current = (p_eq * total_volume) / (DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL * temp_k)
    expected = ((n_initial - n_current) * 1e6) / mass_g
    actual = amount_adsorbed(
        n_initial_mol=n_initial,
        pressure_equilibrium_torr=p_eq,
        total_volume_l=total_volume,
        temperature_k=temp_k,
        mass_g=mass_g,
    )

    assert actual == pytest.approx(expected)


def test_amount_adsorbed_zero_mass_raises_zero_division_error() -> None:
    with pytest.raises(ZeroDivisionError):
        amount_adsorbed(
            n_initial_mol=1e-6,
            pressure_equilibrium_torr=0.5,
            total_volume_l=0.201552,
            temperature_k=298.0,
            mass_g=0.0,
        )


def test_metal_surface_density_matches_legacy_formula() -> None:
    expected = (0.04983 / 100) * (1 / 106.42) * (6.023e23) * (1 / 54.0) * (1e-9**2)
    actual = metal_surface_density(
        metal_load_wt_percent=0.04983,
        molar_mass_g_mol=106.42,
        support_surface_area_m2_g=54.0,
    )

    assert actual == pytest.approx(expected)


def test_metal_surface_density_zero_support_surface_area_raises_zero_division_error() -> None:
    with pytest.raises(ZeroDivisionError):
        metal_surface_density(
            metal_load_wt_percent=0.04983,
            molar_mass_g_mol=106.42,
            support_surface_area_m2_g=0.0,
        )
