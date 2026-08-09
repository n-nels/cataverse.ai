"""Leakage-safe sequential training-example construction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import (
    AREA_COLUMN,
    DEFAULT_TIME_TOLERANCE_S,
    TARGET_COLUMNS,
    TIME_COLUMN,
    TimestampCollision,
)
from .observations import (
    flatten_monomer_rows,
    reference_target_from_flattened,
)


FIT_NOT_YET_ELIGIBLE = "fit_not_yet_eligible"
FIT_MISSING_FOR_CUTOFF = "fit_missing_for_cutoff"
FIT_PARTIALLY_POPULATED = "fit_partially_populated"
FIT_MISSING_FOR_WHOLE_EXPERIMENT = "fit_missing_for_whole_experiment"
FIT_FAILED = "fit_failed"
FIT_VALID = "fit_valid"
SUCCESSFUL_NO_ADSORPTION = "successful_no_adsorption"


@dataclass(frozen=True)
class SequentialExample:
    """One experiment prefix and its complete-series reference target."""

    experiment_id: str
    cutoff_id: str
    cutoff_time_s: float
    final_time_s: float
    observation_times_s: tuple[float, ...]
    observation_area: tuple[float, ...]
    observation_count: int
    q_0: float
    current_fit_values: tuple[float | None, ...]
    current_fit_available: tuple[bool, ...]
    fit_status: str
    fit_r_squared: float | None
    fit_rmse: float | None
    reference_target: tuple[float, ...]
    reference_status: str
    collisions: tuple[TimestampCollision, ...]
    assignment: str | None = None
    csv_path: str | None = None
    json_path: str | None = None
    rf_prediction: tuple[float, ...] | None = None
    rf_prediction_provenance: str | None = None
    reference_provenance: str = ""
    observation_fraction: float = 0.0
    elapsed_time_fraction: float = 0.0
    time_remaining_s: float = 0.0
    fit_coverage_by_parameter: tuple[float, ...] = ()


def _finite_value(value: object) -> float | None:
    """Convert one optional dataframe value to a finite float."""
    if value is None or pd.isna(value):
        return None
    converted = float(value)
    return converted if np.isfinite(converted) else None


def _fit_snapshot(
    row: pd.Series,
    *,
    observation_count: int,
    min_points: int,
    reference_status: str,
    has_complete_fit: bool,
) -> tuple[tuple[float | None, ...], tuple[bool, ...], str, float | None, float | None]:
    """Return current fit values, masks, status, and diagnostics."""
    values = tuple(_finite_value(row.get(column)) for column in TARGET_COLUMNS)
    available = tuple(value is not None for value in values)
    r_squared = _finite_value(row.get("pfo-sec_r^2"))
    rmse = _finite_value(row.get("pfo-sec_rmse"))

    if all(available):
        status = FIT_VALID
    elif any(available):
        status = FIT_PARTIALLY_POPULATED
    elif r_squared is not None or rmse is not None:
        status = FIT_FAILED
    elif reference_status == SUCCESSFUL_NO_ADSORPTION:
        status = SUCCESSFUL_NO_ADSORPTION
    elif observation_count < min_points:
        status = FIT_NOT_YET_ELIGIBLE
    elif has_complete_fit:
        status = FIT_MISSING_FOR_CUTOFF
    else:
        status = FIT_MISSING_FOR_WHOLE_EXPERIMENT
    return values, available, status, r_squared, rmse


def build_sequential_examples(
    frame: pd.DataFrame,
    *,
    experiment_id: str,
    successful: bool,
    min_points: int = 4,
    time_tolerance_s: float = DEFAULT_TIME_TOLERANCE_S,
    assignment: str | None = None,
    csv_path: str | None = None,
    json_path: str | None = None,
    rf_prediction: tuple[float, ...] | None = None,
    rf_prediction_provenance: str | None = None,
) -> tuple[SequentialExample, ...]:
    """Build one prefix example for every valid cutoff.

    The returned example at cutoff index ``i`` contains only rows ``0..i``.
    Complete-series targets and collision metadata remain separate from the
    prefix inputs so future observations cannot enter model features.
    """
    if not experiment_id:
        raise ValueError("experiment_id must not be empty")
    if min_points < 1:
        raise ValueError("min_points must be positive")

    flattened, collisions = flatten_monomer_rows(
        frame, time_tolerance_s=time_tolerance_s
    )
    reference = reference_target_from_flattened(
        flattened,
        successful=successful,
        collisions=collisions,
    )
    final_mask = flattened[TIME_COLUMN] <= reference.final_time_s
    timeline = flattened.loc[final_mask].reset_index(drop=True)
    if timeline.empty:
        raise ValueError("No observations remain through the final time")

    first_time_s = float(timeline[TIME_COLUMN].iloc[0])
    duration_s = reference.final_time_s - first_time_s
    fit_coverage = tuple(
        float(
            (
                timeline[column].notna()
                & np.isfinite(pd.to_numeric(timeline[column], errors="coerce"))
            ).mean()
        )
        for column in TARGET_COLUMNS
    )
    complete = timeline[list(TARGET_COLUMNS)].notna().all(axis=1)
    complete &= np.isfinite(timeline[list(TARGET_COLUMNS)]).all(axis=1)
    has_complete_fit = bool(complete.any())
    examples: list[SequentialExample] = []
    for index, row in timeline.iterrows():
        prefix = timeline.iloc[: index + 1]
        times = tuple(float(value) for value in prefix[TIME_COLUMN])
        areas = tuple(float(value) for value in prefix[AREA_COLUMN])
        fit_values, available, fit_status, r_squared, rmse = _fit_snapshot(
            row,
            observation_count=len(prefix),
            min_points=min_points,
            reference_status=reference.status,
            has_complete_fit=has_complete_fit,
        )
        examples.append(
            SequentialExample(
                experiment_id=experiment_id,
                cutoff_id=f"{experiment_id}:{index:04d}",
                cutoff_time_s=float(row[TIME_COLUMN]),
                final_time_s=reference.final_time_s,
                observation_times_s=times,
                observation_area=areas,
                observation_count=len(prefix),
                q_0=areas[0],
                current_fit_values=fit_values,
                current_fit_available=available,
                fit_status=fit_status,
                fit_r_squared=r_squared,
                fit_rmse=rmse,
                reference_target=reference.values,
                reference_status=reference.status,
                collisions=tuple(
                    collision
                    for collision in collisions
                    if collision.time_max_s <= float(row[TIME_COLUMN])
                ),
                assignment=assignment,
                csv_path=csv_path,
                json_path=json_path,
                rf_prediction=rf_prediction,
                rf_prediction_provenance=rf_prediction_provenance,
                reference_provenance=(
                    "complete_series_fit"
                    if reference.status == FIT_VALID
                    else "successful_no_adsorption_zero_target"
                ),
                observation_fraction=(index + 1) / len(timeline),
                elapsed_time_fraction=(
                    1.0
                    if duration_s <= 0
                    else (float(row[TIME_COLUMN]) - first_time_s) / duration_s
                ),
                time_remaining_s=max(
                    0.0, reference.final_time_s - float(row[TIME_COLUMN])
                ),
                fit_coverage_by_parameter=fit_coverage,
            )
        )
    return tuple(examples)
