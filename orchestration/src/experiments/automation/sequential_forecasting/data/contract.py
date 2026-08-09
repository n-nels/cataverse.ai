"""Shared sequential data-contract constants and provenance types."""

from __future__ import annotations

from dataclasses import dataclass


PEAK_NAME = "monomer_sum"
TIME_COLUMN = "Time (s)"
AREA_COLUMN = "Cumulative_Peak_Area"
TARGET_COLUMNS = (
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
)
DEFAULT_TIME_TOLERANCE_S = 1e-3


@dataclass(frozen=True)
class TimestampCollision:
    """Record of rows merged into one sequential observation."""

    time_min_s: float
    time_max_s: float
    source_rows: tuple[int, ...]
    retained_source_row: int
    files: tuple[str, ...]
    delta_groups: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceTarget:
    """Reference target and provenance for one experiment."""

    values: tuple[float, ...]
    final_time_s: float
    status: str
    collisions: tuple[TimestampCollision, ...]
