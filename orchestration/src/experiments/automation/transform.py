"""
Data transformation for PFO-Sec parameter prediction model.

Phase 2: Extract targets from monomer_sum rows.
Phase 3: Feature engineering for current experiment.
Phase 3b: Derived chain features.
Phase 4: Previous experiment targets.
"""

import logging
from typing import Any

import pandas as pd

from extract import ExperimentRecord, extract_data

logger = logging.getLogger(__name__)


TARGET_COLUMNS = [
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
]


VACUUM_GASES = {"RoughPump", "TurboPump"}


GAS_ENCODING = {
    "": 0,
    "CO2": 1,
    "H2": 2,
    "H2,O2": 3,
    "H2O": 4,
    "H2O,O2": 5,
    "O2": 6,
    "O2,H2": 7,
    "O2,H2O": 8,
}
N_GAS_BITS = 4  # ceil(log2(9)) = 4

MAX_PRETREATMENT_STEPS = 8

STEP_NUMERIC_FIELDS = ["pressure_calc", "temp", "rate", "duration"]
STEP_NUMERIC_FIELDS = ["temp", "duration"]
# STEP_NUMERIC_FIELDS = ["temp"]


class TargetExtractionError(Exception):
    """Raised when target extraction fails for an experiment."""


def extract_targets(csv_path) -> pd.Series:
    """
    Phase 2: Extract target values from monomer_sum rows.

    Filters to Peak_Name == 'monomer_sum', flattens Delta_Groups,
    finds the row with maximum Time (s) where all 6 targets are non-NaN.

    If no rows have all 6 targets populated, returns zeros for all targets.
    This is a useful signal for ML (experiment did not converge).

    Parameters
    ----------
    csv_path : Path
        Path to CarbonylPeakArea CSV file.

    Returns
    -------
    pd.Series
        The 6 target values for the experiment (or zeros if no valid rows).
    """
    csv_data = pd.read_csv(csv_path)

    # Filter to monomer_sum rows
    monomer_rows = csv_data[csv_data["Peak_Name"] == "monomer_sum"].copy()

    if monomer_rows.empty:
        logger.warning("No monomer_sum rows found in %s, returning zeros", csv_path)
        return pd.Series(0.0, index=TARGET_COLUMNS)

    # Flatten Delta_Groups — just work with all rows together
    # Find rows where all 6 targets are non-NaN
    target_cols = [col for col in TARGET_COLUMNS if col in monomer_rows.columns]
    if len(target_cols) != 6:
        logger.warning(
            "Expected 6 target columns, found %d in %s, returning zeros",
            len(target_cols),
            csv_path,
        )
        return pd.Series(0.0, index=TARGET_COLUMNS)

    valid_rows = monomer_rows.dropna(subset=target_cols)

    if valid_rows.empty:
        logger.info("No rows with all 6 targets populated in %s, returning zeros", csv_path)
        return pd.Series(0.0, index=TARGET_COLUMNS)

    # Find row with maximum Time (s)
    max_time_idx = valid_rows["Time (s)"].idxmax()
    targets = valid_rows.loc[max_time_idx, target_cols]

    return targets


def normalize_pressure_calc(
    pressure_calc: Any,
    gas: list[str],
    pressure_meas_g1: float | None,
) -> float:
    """
    Normalize pressure_calc value.

    Rules:
    - If pressure_calc is not null: extract scalar from list
    - If pressure_calc is null AND gas is vacuum: use 0
    - If pressure_calc is null AND gas is not vacuum: use pressure_meas_g1

    Parameters
    ----------
    pressure_calc : Any
        Raw pressure_calc value from JSON (null or list).
    gas : list[str]
        List of gas names for this step.
    pressure_meas_g1 : float | None
        Measured pressure to use as fallback.

    Returns
    -------
    float
        Normalized pressure value.

    Raises
    ------
    ValueError
        If pressure_calc is null for non-vacuum gas and no fallback is available.
    """
    if pressure_calc is not None:
        # Extract scalar from list
        if isinstance(pressure_calc, list) and len(pressure_calc) > 0:
            return float(pressure_calc[0])
        return float(pressure_calc)

    # pressure_calc is null
    gas_set = set(gas)
    if gas_set & VACUUM_GASES:
        return 0.0

    # Non-vacuum gas with null pressure_calc — use fallback
    if pressure_meas_g1 is not None:
        return float(pressure_meas_g1)

    logger.warning(
        "pressure_calc is null for non-vacuum gas %s with no fallback", gas
    )
    raise ValueError(
        "Cannot determine pressure_calc for non-vacuum gas with no fallback"
    )


def gas_list_to_combo(gas: list[str]) -> str:
    """Convert gas list to comma-joined string for one-hot encoding."""
    return ",".join(gas) if gas else ""


def extract_step_features(step: dict) -> dict[str, float | str]:
    """
    Extract features from a single pretreatment step.

    Returns dict with keys: gas_combo, pressure_calc, temp, rate, duration.
    """
    gas = step.get("gas", [])
    gas_combo = gas_list_to_combo(gas)

    pressure_calc = normalize_pressure_calc(
        step.get("pressure_calc"),
        gas,
        step.get("pressure_meas_g1"),
    )

    return {
        "gas_combo": gas_combo,
        "pressure_calc": pressure_calc,
        "temp": float(step.get("temp")),
        "rate": float(step.get("rate")),
        "duration": float(step.get("duration")),
    }


def extract_pretreatment_features(json_data: dict) -> dict[str, float]:
    """
    Phase 3: Extract pretreatment features from JSON.

    Flattens pretreatments to MAX_PRETREATMENT_STEPS, pads missing steps.
    Each step produces: gas_onehot_<combo>, pressure_calc, temp, rate, duration.

    Parameters
    ----------
    json_data : dict
        Parsed JSON experiment data.

    Returns
    -------
    dict[str, float]
        Flattened pretreatment features.
    """
    pretreatments = json_data.get("pretreatments", [])
    features = {}

    for step_idx in range(MAX_PRETREATMENT_STEPS):
        prefix = f"pre_{step_idx + 1}"

        if step_idx < len(pretreatments):
            step = pretreatments[step_idx]
            step_features = extract_step_features(step)
        else:
            # Padding — all zeros
            step_features = {
                "gas_combo": "",
                "pressure_calc": 0.0,
                "temp": 0.0,
                "rate": 0.0,
                "duration": 0.0,
            }

        # Gas binary encoding (4 bits, no ordinal bias)
        gas_value = GAS_ENCODING.get(step_features["gas_combo"], 0)
        for bit in range(N_GAS_BITS):
            features[f"{prefix}_gas_bit{bit}"] = float((gas_value >> bit) & 1)

        # # Gas one-hot encoding (single column with categorical values)
        # features[f"{prefix}_gas"] = float(GAS_ENCODING.get(step_features["gas_combo"], 0))

        # Numeric fields
        for field in STEP_NUMERIC_FIELDS:
            features[f"{prefix}_{field}"] = step_features[field]

    return features


def extract_exp_conditions_features(json_data: dict) -> dict[str, float]:
    """
    Extract exp_conditions features from JSON.

    Parameters
    ----------
    json_data : dict
        Parsed JSON experiment data.

    Returns
    -------
    dict[str, float]
        Exp conditions features (exp_pressure_calc, exp_temp).
    """
    exp_conds = json_data.get("exp_conditions", {})
    features = {}

    gas = exp_conds.get("gas", [])

    # pressure_calc
    features["exp_pressure_calc"] = normalize_pressure_calc(
        exp_conds.get("pressure_calc"),
        gas,
        exp_conds.get("pressure_meas_g1"),
    )

    # temp
    features["exp_temp"] = float(exp_conds.get("temp"))

    return features


def extract_current_features(json_data: dict) -> dict[str, float]:
    """
    Phase 3: Extract all features for the current experiment.

    Includes:
    - is_new, is_reference, metal_loading
    - Pretreatment features (8 steps padded)
    - Exp conditions features

    Parameters
    ----------
    json_data : dict
        Parsed JSON experiment data.

    Returns
    -------
    dict[str, float]
        All current experiment features.
    """
    features = {}

    # Metadata features
    material = json_data.get("material", {})
    flags = json_data.get("filename_flags", {})

    features["is_new"] = 1.0 if flags.get("is_new") else 0.0
    features["is_reference"] = 1.0 if flags.get("is_reference") else 0.0
    features["metal_loading"] = float(material.get("metal_loading", 0.0) or 0.0)

    # Pretreatment features
    features.update(extract_pretreatment_features(json_data))

    # Exp conditions features
    features.update(extract_exp_conditions_features(json_data))

    return features


def compute_chain_features(
    records: list[ExperimentRecord],
) -> list[dict[str, float]]:
    """
    Phase 3b: Compute derived chain features for each experiment.

    Features computed:
    - distance_from_isnew: count since last is_new=true
    - consecutive_isref: count of consecutive is_reference=true
    - distance_from_isref: count of consecutive is_reference=false since last is_reference=true

    Parameters
    ----------
    records : list[ExperimentRecord]
        Chronologically sorted experiment records.

    Returns
    -------
    list[dict[str, float]]
        Chain features for each record (same order as input).
    """
    chain_features = []

    # Per-notebook state tracking
    notebook_state: dict[str, dict[str, int]] = {}

    for rec in records:
        # Extract notebook from json_data (use base_name prefix or material.notebook)
        json_data = rec.json_data
        material = json_data.get("material")
        notebook = material.get("notebook", rec.base_name.rsplit("_", 1)[0])

        if notebook not in notebook_state:
            notebook_state[notebook] = {
                "distance_from_isnew": 0,
                "consecutive_isref": 0,
                "distance_from_isref": 0,
            }

        state = notebook_state[notebook]
        flags = json_data.get("filename_flags", {})
        is_new = flags.get("is_new")
        is_reference = flags.get("is_reference")

        # Compute distance_from_isnew
        if is_new:
            state["distance_from_isnew"] = 0
        else:
            state["distance_from_isnew"] += 1

        # Compute consecutive_isref
        if is_reference:
            state["consecutive_isref"] += 1
        else:
            state["consecutive_isref"] = 0

        # Compute distance_from_isref
        if is_reference:
            state["distance_from_isref"] = 0
        else:
            state["distance_from_isref"] += 1

        chain_features.append({
            "distance_from_isnew": float(state["distance_from_isnew"]),
            "consecutive_isref": float(state["consecutive_isref"]),
            "distance_from_isref": float(state["distance_from_isref"]),
        })

    return chain_features


def add_previous_targets(
    records: list[ExperimentRecord],
    all_targets: list[pd.Series],
    prev_target_columns: list[str] | None = None,
) -> list[dict[str, float]]:
    """
    Phase 4: Add previous experiment targets as features.

    For each experiment, appends target values from the previous
    experiment in the same notebook. First experiment in chain uses zeros.

    Parameters
    ----------
    records : list[ExperimentRecord]
        Chronologically sorted experiment records.
    all_targets : list[pd.Series]
        Target values for each record (same order).
    prev_target_columns : list[str] | None
        Which target columns to include as previous-target features.
        Default ``TARGET_COLUMNS[1:2]`` (only ``pfo-sec_q_e_au``).

    Returns
    -------
    list[dict[str, float]]
        Previous target features for each record.
    """
    if prev_target_columns is None:
        prev_target_columns = TARGET_COLUMNS[1:2]

    prev_features = []

    # Per-notebook state: last targets seen (full 6-column series)
    notebook_last_targets: dict[str, pd.Series | None] = {}

    for rec, targets in zip(records, all_targets):
        json_data = rec.json_data
        material = json_data.get("material")
        notebook = material.get("notebook", rec.base_name.rsplit("_", 1)[0])

        last_targets = notebook_last_targets.get(notebook)

        if last_targets is None:
            # First experiment in chain — use zeros
            prev_features.append(
                {f"prev_{col}": 0.0 for col in prev_target_columns}
            )
        else:
            prev_features.append(
                {f"prev_{col}": float(last_targets[col]) for col in prev_target_columns}
            )

        # Update state with current targets (full series for next lookup)
        notebook_last_targets[notebook] = targets

    return prev_features
