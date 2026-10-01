"""Classify and kinetics-fit one measurement's area CSV (live-equivalent).

Also holds the module-level singletons (``UTILS``, ``MODELS``, ``WRITER``)
the rest of the package uses.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.core import config

from .classification import (
    classify_nucleation,
    latch_sweep,
    nucleation_trajectory,
    sorted_trajectory,
)
from .models import KineticModels, _ModelRowSpec
from .utils import _KineticUtilities

SEARCH_ROOT = Path(config.get_path("data.peak_fit"))
AREA_SUFFIX = config.get_setting("filenames.carbonyl_fit.area_suffix")

# Kinetic model per (peak group, regime). The regime of a time point is the
# causal nucleation latch state at that time (classification.classify_nucleation). The discontinuous entries are
# placeholders (the continuous model on the expanding window) until the
# before/after-detection models exist -- that work only fills in this table.
REGIME_MODELS: dict[tuple[str, str], str] = {
    ("monomer", "continuous"): "secondary_pfo",
    ("monomer", "discontinuous"): "secondary_pfo",
    ("cluster", "continuous"): "pfo",
    ("cluster", "discontinuous"): "pfo",
}
SUM_OF_GROUP = {"monomer": "monomer_sum", "cluster": "cluster_sum"}

AREA_COLUMNS = [
    "File",
    "Delta_Group",
    "Peak_Name",
    "Peak_Center",
    "Time (s)",
    "Cumulative_Peak_Area",
    "Cumulative_Integral",
]
CLASSIFICATION_COLUMNS = ["classification", "growth_onset_s"]


class KineticWriter:
    """Prepare fit rows and write outputs."""

    def __init__(
        self,
        utils: _KineticUtilities,
        models: KineticModels,
    ) -> None:
        self.utils = utils
        self.models = models
        self.model_specs: dict[str, _ModelRowSpec] = {
            "pfo": _ModelRowSpec(
                r2_col="pfo_r^2",
                rmse_col="pfo_rmse",
                param_map=[
                    ("pfo_k_s-1", "pfo_k_stderr"),
                    ("pfo_q_e_au", "pfo_q_e_stderr"),
                    ("pfo_q0_au", None),
                ],
                fit_fn=self.models.registry["pfo"],
            ),
            "secondary_pfo": _ModelRowSpec(
                r2_col="pfo-sec_r^2",
                rmse_col="pfo-sec_rmse",
                param_map=[
                    ("pfo-sec_k_a_s-1", "pfo-sec_k_a_stderr"),
                    ("pfo-sec_q_e_au", "pfo-sec_q_e_stderr"),
                    ("pfo-sec_k_s_s-1", "pfo-sec_k_s_stderr"),
                    ("pfo-sec_k_p_s-1", "pfo-sec_k_p_stderr"),
                    ("pfo-sec_q_inf_au", "pfo-sec_q_inf_stderr"),
                    ("pfo-sec_q0_au", None),
                ],
                fit_fn=self.models.registry["secondary_pfo"],
            ),
        }

    def _select_secondary_p0(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        *,
        threshold_r2: float = 0.96,
        user_p0: list[float] | None = None,
        min_points: int = 4,
    ) -> list[float]:
        """Choose secondary_pfo p0 for the current trajectory slice."""
        if len(time_s) < min_points:
            return user_p0 if user_p0 is not None else [3e-4, 1.0, 5e-5, 0.5, 0.0]

        q_guess = float(np.max(intensity)) if intensity.size else 0.0
        default_p0 = [3e-4, q_guess, 5e-5, 0.5, 0.0]
        current = list(user_p0) if user_p0 is not None else list(default_p0)
        if len(current) != 5:
            current = list(default_p0)

        best_p0 = list(current)
        best_r2 = -np.inf

        fit_fn = self.models.registry["secondary_pfo"]

        def eval_r2(candidate: list[float]) -> float:
            _, _, r2, _ = fit_fn(time_s, intensity, candidate)
            return float(r2) if np.isfinite(r2) else -np.inf

        baseline_r2 = eval_r2(best_p0)
        best_r2 = max(best_r2, baseline_r2)
        if best_r2 >= threshold_r2:
            return best_p0

        search_steps: list[tuple[int, list[float]]] = [
            (0, [3e-5, 6e-4]),  # k_a
            (1, [q_guess / 2.0]),  # q_e
            (2, [9e-5, 1e-5]),  # k_s
            (3, [0.1, 1.0]),  # k_p_ratio
            (4, [0.5]),  # q_inf
        ]

        for param_idx, trial_values in search_steps:
            local_best_p0 = list(best_p0)
            local_best_r2 = best_r2

            for trial in trial_values:
                candidate = list(best_p0)
                candidate[param_idx] = float(trial)
                r2 = eval_r2(candidate)
                if r2 > local_best_r2:
                    local_best_r2 = r2
                    local_best_p0 = candidate

            best_p0 = local_best_p0
            best_r2 = local_best_r2
            if best_r2 >= threshold_r2:
                return best_p0

        return best_p0

    def _select_secondary_p0_for_secondary(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        *,
        model_key: str,
        use_prior_p0: bool,
        previous_p0: list[float] | None,
        previous_r2: float | None,
        min_points: int,
    ) -> list[float] | None:
        """Select effective p0 for secondary_pfo, respecting the ``use_prior_p0`` toggle.

        pfo takes no p0 (its fit uses built-in defaults).
        """
        if model_key != "secondary_pfo":
            return None

        # use_prior_p0: seed the search from the last successful p0; otherwise
        # start fresh from the defaults inside _select_secondary_p0, as live does.
        seed_p0 = previous_p0 if use_prior_p0 and previous_r2 is not None else None
        return self._select_secondary_p0(
            time_s,
            intensity,
            threshold_r2=0.96,
            user_p0=seed_p0,
            min_points=min_points,
        )

    def kinetic_columns(self) -> list[str]:
        """Kinetic output columns, in the live ``*_CarbonylPeakArea.csv`` order."""
        columns = list(CLASSIFICATION_COLUMNS)
        for key in ("secondary_pfo", "pfo"):
            spec = self.model_specs[key]
            columns += [spec.r2_col, spec.rmse_col]
            for value_key, stderr_key in spec.param_map:
                columns.append(value_key)
                if stderr_key is not None:
                    columns.append(stderr_key)
        return columns

    def classify_by_time(
        self,
        df: pd.DataFrame,
        *,
        min_points: int = 4,
    ) -> dict[float, dict[str, Any]]:
        """Causal per-time nucleation classification (written on ``cluster_sum``).

        Runs ``classification.latch_sweep`` of ``classify_nucleation`` once over
        the time-sorted ``nucleation_trajectory`` (the same sweep the
        ground-truth harness scores). A time is ``discontinuous`` once the
        latch has engaged at or before its last row (rows sharing a time, one
        per Delta_Group, take the state after the last of them), ``continuous``
        before that, and NaN while fewer than ``min_points`` points exist.
        Latched times also carry ``growth_onset_s``: the latch time.
        """
        time_s, payload = nucleation_trajectory(df)
        if time_s.size == 0:
            return {}
        latch = latch_sweep(classify_nucleation, time_s, payload, min_points=min_points)
        latched_extra: dict[str, Any] = {}
        if latch.n_points is not None:
            onset = latch.result.get("growth_onset_s")
            latched_extra["growth_onset_s"] = (
                float(onset) if onset is not None else np.nan
            )

        by_time: dict[float, dict[str, Any]] = {}
        for unique_time in np.unique(time_s):
            n_points = int(np.searchsorted(time_s, unique_time, side="right"))
            if n_points < min_points:
                by_time[float(unique_time)] = {"classification": np.nan}
            elif latch.n_points is not None and n_points >= latch.n_points:
                by_time[float(unique_time)] = {
                    "classification": "discontinuous",
                    **latched_extra,
                }
            else:
                by_time[float(unique_time)] = {"classification": "continuous"}
        return by_time

    def _fit_trajectory_rolling(
        self,
        peak_name: str,
        group: str,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        regime_of: Callable[[float], str],
        *,
        min_points: int,
        carry_forward_p0: bool,
    ) -> list[dict[str, Any]]:
        """Expanding-window fit at every unique time (live ``latest_only=False``)."""
        records: list[dict[str, Any]] = []
        previous_model: str | None = None
        previous_p0: list[float] | None = None
        previous_r2: float | None = None
        for unique_time in np.unique(time_s):
            mask = time_s <= unique_time
            if int(mask.sum()) < min_points:
                continue
            model_key = REGIME_MODELS[(group, regime_of(float(unique_time)))]
            if model_key != previous_model:
                previous_p0, previous_r2 = None, None
                previous_model = model_key
            spec = self.model_specs[model_key]
            t_slice, y_slice = time_s[mask], intensity[mask]
            effective_p0 = self._select_secondary_p0_for_secondary(
                t_slice,
                y_slice,
                model_key=model_key,
                use_prior_p0=carry_forward_p0,
                previous_p0=previous_p0,
                previous_r2=previous_r2,
                min_points=min_points,
            )
            popt, std_errors, r_squared, rmse = spec.fit_fn(
                t_slice, y_slice, effective_p0
            )
            if (
                model_key == "secondary_pfo"
                and carry_forward_p0
                and np.isfinite(r_squared)
                and (previous_r2 is None or r_squared > previous_r2 + 0.01)
            ):
                previous_p0 = list(effective_p0) if effective_p0 is not None else None
                previous_r2 = float(r_squared)

            record: dict[str, Any] = {
                "Peak_Name": peak_name,
                "Time (s)": float(unique_time),
                spec.r2_col: r_squared,
                spec.rmse_col: rmse,
            }
            for idx, (value_key, stderr_key) in enumerate(spec.param_map):
                value = popt[idx] if idx < len(popt) else np.nan
                record[value_key] = float(value) if np.isfinite(value) else np.nan
                if stderr_key is not None:
                    stderr = std_errors[idx] if idx < len(std_errors) else np.nan
                    record[stderr_key] = float(stderr) if np.isfinite(stderr) else np.nan
            records.append(record)
        return records

    def prepare_measurement_rows(
        self,
        df_area: pd.DataFrame,
        *,
        fit: bool = True,
        min_points: int = 4,
        carry_forward_p0: bool = False,
        groups: dict[str, list[str]] | None = None,
        peak_names: list[str] | None = None,
    ) -> pd.DataFrame:
        """Kinetics rows for one measurement, keyed by ``(Peak_Name, Time (s))``.

        Args:
            df_area: The measurement's area frame (sums already baked in).
            fit: False writes classification only (no kinetic fits).
            min_points: Minimum points before classifying or fitting.
            carry_forward_p0: Seed each time point's secondary_pfo p0 search
                from the previous one. Off by default: live searches fresh
                at every point.
            groups: ``{"monomer": [...], "cluster": [...]}`` atomic peaks.
                ``None`` = the ``ir_fitting.fit`` groups.
            peak_names: Optional restriction of which rows are fitted.
        """
        df = df_area.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        by_time = self.classify_by_time(df, min_points=min_points)
        records: dict[tuple[str, float], dict[str, Any]] = {
            ("cluster_sum", t): {"Peak_Name": "cluster_sum", "Time (s)": t, **payload}
            for t, payload in by_time.items()
        }

        def regime_of(time_value: float) -> str:
            label = by_time.get(time_value, {}).get("classification")
            return "discontinuous" if label == "discontinuous" else "continuous"

        if fit:
            groups = groups or {
                group: self.utils.group_peak_names(group) for group in SUM_OF_GROUP
            }
            for group, atomic in groups.items():
                for peak_name in [*atomic, SUM_OF_GROUP[group]]:
                    if peak_names is not None and peak_name not in peak_names:
                        continue
                    time_s, intensity = sorted_trajectory(df, peak_name)
                    for record in self._fit_trajectory_rolling(
                        peak_name,
                        group,
                        time_s,
                        intensity,
                        regime_of,
                        min_points=min_points,
                        carry_forward_p0=carry_forward_p0,
                    ):
                        key = (peak_name, record["Time (s)"])
                        records.setdefault(key, {}).update(record)

        if not records:
            return pd.DataFrame(columns=["Peak_Name", "Time (s)", *self.kinetic_columns()])
        rows = pd.DataFrame(list(records.values()))
        # Every kinetic column is always present (stable schema).
        return rows.reindex(
            columns=["Peak_Name", "Time (s)", *self.kinetic_columns()]
        )

    def write_measurement(
        self,
        area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        **kwargs: Any,
    ) -> tuple[Path, pd.DataFrame]:
        """Classify (and fit) one area CSV and write it to ``output_folder_name``.

        The output is the area frame, unchanged and in its row order, with the
        kinetic columns left-joined on ``(Peak_Name, Time (s))``. It is built
        fresh, so no kinetics from an earlier run can leak in.
        """
        area_path = Path(area_path)
        df_area = pd.read_csv(area_path)
        df_area = df_area.drop(
            columns=[c for c in df_area.columns if c not in AREA_COLUMNS]
        )
        rows = self.prepare_measurement_rows(df_area, **kwargs)
        df_area["Time (s)"] = pd.to_numeric(df_area["Time (s)"], errors="coerce")
        merged = df_area.merge(rows, on=["Peak_Name", "Time (s)"], how="left")
        output_dir = self.utils.resolve_output_dir(area_path.parent, output_folder_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / area_path.name
        merged.to_csv(output_path, index=False)
        return output_path, rows

# --- Instances ---
UTILS = _KineticUtilities()
MODELS = KineticModels(UTILS)
WRITER = KineticWriter(UTILS, MODELS)
