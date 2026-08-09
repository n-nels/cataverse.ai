"""Data-contract helpers for sequential forecasting."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd


LOGGER = logging.getLogger(__name__)

from .contract import (
    AREA_COLUMN,
    DEFAULT_TIME_TOLERANCE_S,
    PEAK_NAME,
    TARGET_COLUMNS,
    TIME_COLUMN,
    ReferenceTarget,
    TimestampCollision,
)


def _collision_from_group(group: pd.DataFrame) -> TimestampCollision:
    """Build a collision record from one time cluster."""
    source_rows = tuple(int(value) for value in group["_source_row"])
    retained_source_row = max(source_rows)
    files = (
        tuple(str(value) for value in group["File"])
        if "File" in group
        else ("",) * len(group)
    )
    delta_groups = (
        tuple(str(value) for value in group["Delta_Group"])
        if "Delta_Group" in group
        else ("",) * len(group)
    )
    return TimestampCollision(
        time_min_s=float(group[TIME_COLUMN].min()),
        time_max_s=float(group[TIME_COLUMN].max()),
        source_rows=source_rows,
        retained_source_row=retained_source_row,
        files=files,
        delta_groups=delta_groups,
    )


def flatten_monomer_rows(
    frame: pd.DataFrame,
    *,
    time_tolerance_s: float = DEFAULT_TIME_TOLERANCE_S,
) -> tuple[pd.DataFrame, tuple[TimestampCollision, ...]]:
    """Filter and flatten monomer observations by tolerant timestamp.

    Rows are sorted by time to identify clusters within ``time_tolerance_s``.
    The last row in original CSV order is retained for each cluster, matching
    the existing kinetics writer. Every merged cluster is returned as a
    :class:`TimestampCollision` and logged.
    """
    if time_tolerance_s < 0:
        raise ValueError("time_tolerance_s must be non-negative")
    required = {"Peak_Name", TIME_COLUMN, AREA_COLUMN}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required observation columns: {sorted(missing)}")

    monomer = frame.loc[frame["Peak_Name"] == PEAK_NAME].copy()
    monomer["_source_row"] = np.arange(len(frame), dtype=int)[
        frame["Peak_Name"].to_numpy() == PEAK_NAME
    ]
    monomer[TIME_COLUMN] = pd.to_numeric(monomer[TIME_COLUMN], errors="coerce")
    monomer[AREA_COLUMN] = pd.to_numeric(monomer[AREA_COLUMN], errors="coerce")
    monomer = monomer.dropna(subset=[TIME_COLUMN, AREA_COLUMN])
    monomer = monomer.loc[
        np.isfinite(monomer[TIME_COLUMN]) & np.isfinite(monomer[AREA_COLUMN])
    ]
    if monomer.empty:
        return monomer.drop(columns=["_source_row"]), ()

    ordered = monomer.sort_values(TIME_COLUMN, kind="stable")
    clusters: list[list[int]] = []
    current: list[int] = []
    cluster_start = 0.0
    for index, row in ordered.iterrows():
        time_s = float(row[TIME_COLUMN])
        if not current or time_s - cluster_start <= time_tolerance_s:
            if not current:
                cluster_start = time_s
            current.append(index)
        else:
            clusters.append(current)
            current = [index]
            cluster_start = time_s
    if current:
        clusters.append(current)

    selected_rows: list[pd.Series] = []
    collisions: list[TimestampCollision] = []
    for cluster_indices in clusters:
        group = ordered.loc[cluster_indices]
        collision = _collision_from_group(group)
        if len(cluster_indices) > 1:
            collisions.append(collision)
            LOGGER.info(
                "Merged timestamp collision: %.6f-%.6f s; retained source row %d; "
                "files=%s; delta_groups=%s",
                collision.time_min_s,
                collision.time_max_s,
                collision.retained_source_row,
                collision.files,
                collision.delta_groups,
            )
        retained = group.loc[group["_source_row"].idxmax()]
        selected_rows.append(retained)

    flattened = pd.DataFrame(selected_rows).sort_values(TIME_COLUMN, kind="stable")
    flattened = flattened.drop(columns=["_source_row"]).reset_index(drop=True)
    if collisions:
        LOGGER.warning("Merged %d monomer timestamp collisions", len(collisions))
    return flattened, tuple(collisions)


def extract_reference_target(
    frame: pd.DataFrame,
    *,
    successful: bool,
    time_tolerance_s: float = DEFAULT_TIME_TOLERANCE_S,
) -> ReferenceTarget:
    """Extract a complete-series target or a valid zero target.

    Successful experiments without a complete stored fit are treated as
    successful-no-adsorption records and receive six zero target values.
    Unsuccessful records are rejected because the upstream ETL excludes them.
    """
    if not successful:
        raise ValueError("Unsuccessful experiments must be excluded by the ETL")

    flattened, collisions = flatten_monomer_rows(
        frame, time_tolerance_s=time_tolerance_s
    )
    if flattened.empty:
        raise ValueError("No valid monomer observations found")

    return reference_target_from_flattened(
        flattened,
        successful=successful,
        collisions=collisions,
    )


def reference_target_from_flattened(
    flattened: pd.DataFrame,
    *,
    successful: bool,
    collisions: tuple[TimestampCollision, ...] = (),
) -> ReferenceTarget:
    """Extract a reference target from already-flattened observations."""
    if not successful:
        raise ValueError("Unsuccessful experiments must be excluded by the ETL")
    if flattened.empty:
        raise ValueError("No valid monomer observations found")

    complete = flattened[list(TARGET_COLUMNS)].notna().all(axis=1)
    complete &= np.isfinite(flattened[list(TARGET_COLUMNS)]).all(axis=1)
    if complete.any():
        row = flattened.loc[complete].sort_values(TIME_COLUMN).iloc[-1]
        first_area = float(flattened.sort_values(TIME_COLUMN).iloc[0][AREA_COLUMN])
        values = tuple(float(row[column]) for column in TARGET_COLUMNS[:-1]) + (
            first_area,
        )
        return ReferenceTarget(
            values=values,
            final_time_s=float(row[TIME_COLUMN]),
            status="fit_valid",
            collisions=collisions,
        )

    return ReferenceTarget(
        values=(0.0,) * len(TARGET_COLUMNS),
        final_time_s=float(flattened[TIME_COLUMN].max()),
        status="successful_no_adsorption",
        collisions=collisions,
    )
