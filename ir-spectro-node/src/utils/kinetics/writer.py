"""Prepare kinetics fit/classification rows and write legacy-merged CSV outputs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config

from .classification import KineticClassification
from .models import KineticModels, _ModelRowSpec
from .utils import _KineticUtilities

SEARCH_ROOT = Path(config.get_path("data.peak_fit"))
AREA_SUFFIX = config.get_setting("filenames.carbonyl_fit.area_suffix")


class KineticWriter:
    """Prepare fit rows and write outputs."""

    def __init__(
        self,
        utils: _KineticUtilities,
        models: KineticModels,
        classifier: KineticClassification,
    ) -> None:
        self.utils = utils
        self.models = models
        self.classifier = classifier
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

    def _prepare_model_rows_for_file(
        self,
        model_key: str,
        df_legacy: pd.DataFrame,
        *,
        min_points: int,
        peak_names: list[str] | None,
        mode: str,
        p0: list[float] | None,
        carry_forward_p0: bool,
        monomer_sum_peaks: list[str] | None = None,
        cluster_sum_peaks: list[str] | None = None,
    ) -> pd.DataFrame:
        return self.prepare_model_fit_rows(
            model_key,
            df_legacy,
            min_points=min_points,
            peak_names=peak_names,
            mode=mode,
            p0=p0,
            carry_forward_p0=carry_forward_p0,
            monomer_sum_peaks=monomer_sum_peaks,
            cluster_sum_peaks=cluster_sum_peaks,
        )

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
        if baseline_r2 > best_r2:
            best_r2 = baseline_r2
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
        user_p0: list[float] | None,
        min_points: int,
    ) -> list[float] | None:
        """Select effective p0 for secondary_pfo, respecting the ``use_prior_p0`` toggle."""
        if model_key != "secondary_pfo":
            return user_p0

        if not use_prior_p0:
            # Start fresh each row: seed from user p0 (or default inside _select_secondary_p0).
            return self._select_secondary_p0(
                time_s,
                intensity,
                threshold_r2=0.96,
                user_p0=user_p0,
                min_points=min_points,
            )

        # use_prior_p0=True: carry forward successful p0 between rows.
        seed_p0 = previous_p0 if previous_r2 is not None else user_p0
        return self._select_secondary_p0(
            time_s,
            intensity,
            threshold_r2=0.96,
            user_p0=seed_p0,
            min_points=min_points,
        )

    def _classification_payload(
        self,
        group: pd.DataFrame,
        peak_name: str,
        min_points: int,
        classify_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> tuple[float | str, float | str, dict[str, Any]]:
        classification_value: float | str = np.nan
        breakpoint_used_value: float | str = np.nan
        classification: dict[str, Any] = {}

        if peak_name == "cluster_sum" and len(group) >= min_points:
            time_s_all = group["Time (s)"].to_numpy(dtype=float)
            intensity_all = group["Cumulative_Peak_Area"].to_numpy(dtype=float)
            classify = (
                classify_fn
                if classify_fn is not None
                else self.classifier.classify_trajectory_combined
            )
            classification = classify(time_s_all, intensity_all)
            for key, value in classification.items():
                if (key.startswith("pre_") or key.startswith("post_")) and isinstance(
                    value, float
                ):
                    classification[key] = float(value)

            classification_raw = classification.get("classification")
            classification_value = (
                str(classification_raw) if classification_raw is not None else np.nan
            )
            breakpoint_raw = classification.get("growth_onset_s")
            breakpoint_used_value = (
                float(breakpoint_raw) if breakpoint_raw is not None else np.nan
            )

        return classification_value, breakpoint_used_value, classification

    def prepare_model_fit_rows(
        self,
        model_key: str,
        df: pd.DataFrame,
        *,
        min_points: int = 4,
        peak_names: list[str] | None = None,
        mode: str = "rolling",
        p0: list[float] | None = None,
        carry_forward_p0: bool = True,
        monomer_sum_peaks: list[str] | None = None,
        cluster_sum_peaks: list[str] | None = None,
    ) -> pd.DataFrame:
        """Prepare fit-result rows for one DataFrame.

        Parameters
        ----------
        model_key : str
            Which model to fit: ``"pfo"`` or ``"secondary_pfo"``.
        df : pd.DataFrame
            CarbonylPeakArea data with ``Peak_Name``, ``Time (s)``,
            and ``Cumulative_Peak_Area`` columns.
        min_points : int
            Minimum data points required before fitting a peak group.
        peak_names : list[str] | None
            Restrict fitting to these peak names.  None = all peaks.
        mode : str
            ``"rolling"`` — for each time point, fit using all data up
            to and including that time (expanding window).  Produces one
            row per time point per peak.
            ``"full_series"`` — fit once using all data, producing one
            row per peak at the latest time.
        p0 : list[float] | None
            User-supplied initial guess for the optimizer.  None = use
            built-in defaults.
        carry_forward_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            ``p0`` (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        monomer_sum_peaks : list[str] | None
            Override which Peak_Name rows get summed into ``monomer_sum``.
            None = use the config-defined definition (or the input CSV's
            existing monomer_sum row, if already present).
        cluster_sum_peaks : list[str] | None
            Same override, for ``cluster_sum``.
        """
        spec = self.model_specs.get(model_key)
        if spec is None:
            raise ValueError(f"Unknown model_key: {model_key}")
        if mode not in {"rolling", "full_series"}:
            raise ValueError("mode must be one of: rolling, full_series")

        df = self.utils.prepare_peak_area_df(
            df,
            monomer_sum_peaks=monomer_sum_peaks,
            cluster_sum_peaks=cluster_sum_peaks,
        )
        if peak_names is not None:
            df = cast(pd.DataFrame, df[df["Peak_Name"].isin(peak_names)].copy())

        records: list[dict[str, float | str]] = []
        for group_key, group_raw in df.groupby("Peak_Name"):
            group = cast(
                pd.DataFrame, group_raw.sort_values("Time (s)").reset_index(drop=True)
            )
            peak_name = str(group_key)

            previous_p0: list[float] | None = None
            previous_r2: float | None = None
            r2_improvement_threshold = 0.01

            classification_value, breakpoint_used_value, classification = (
                self._classification_payload(group, peak_name, min_points)
            )

            if len(group) < min_points:
                continue

            if mode == "full_series":
                unique_time = float(group["Time (s)"].max())
                time_s = group["Time (s)"].to_numpy(dtype=float)
                intensity = group["Cumulative_Peak_Area"].to_numpy(dtype=float)
                if len(time_s) < min_points:
                    continue
                current_row = group[group["Time (s)"] == unique_time].iloc[0]
                effective_p0 = self._select_secondary_p0_for_secondary(
                    time_s,
                    intensity,
                    model_key=model_key,
                    use_prior_p0=carry_forward_p0,
                    previous_p0=previous_p0,
                    previous_r2=previous_r2,
                    user_p0=p0,
                    min_points=min_points,
                )
                popt, std_errors, r_squared, rmse = spec.fit_fn(
                    time_s, intensity, effective_p0
                )
                if (
                    model_key == "secondary_pfo"
                    and carry_forward_p0
                    and np.isfinite(r_squared)
                    and (
                        previous_r2 is None
                        or r_squared > previous_r2 + r2_improvement_threshold
                    )
                ):
                    previous_p0 = (
                        list(effective_p0) if effective_p0 is not None else None
                    )
                    previous_r2 = float(r_squared)

                record: dict[str, float | str] = {
                    "Peak_Name": str(current_row["Peak_Name"]),
                    "Time (s)": float(unique_time),
                    spec.r2_col: r_squared,
                    spec.rmse_col: rmse,
                    "classification": classification_value,
                    "growth_onset_s": breakpoint_used_value,
                }

                if (
                    peak_name == "cluster_sum"
                    and classification_value == "discontinuous"
                ):
                    for key, value in classification.items():
                        if key.startswith("pre_") or key.startswith("post_"):
                            record[key] = value

                for idx, (value_key, stderr_key) in enumerate(spec.param_map):
                    value = popt[idx] if idx < len(popt) else np.nan
                    record[value_key] = float(value) if np.isfinite(value) else np.nan
                    if stderr_key is not None:
                        stderr = std_errors[idx] if idx < len(std_errors) else np.nan
                        record[stderr_key] = (
                            float(stderr) if np.isfinite(stderr) else np.nan
                        )

                records.append(record)
            else:
                for unique_time in sorted(group["Time (s)"].unique()):
                    mask = group["Time (s)"] <= unique_time
                    time_s = group.loc[mask, "Time (s)"].to_numpy(dtype=float)
                    intensity = group.loc[mask, "Cumulative_Peak_Area"].to_numpy(
                        dtype=float
                    )
                    if len(time_s) < min_points:
                        continue

                    current_row = group[group["Time (s)"] == unique_time].iloc[0]
                    effective_p0 = self._select_secondary_p0_for_secondary(
                        time_s,
                        intensity,
                        model_key=model_key,
                        use_prior_p0=carry_forward_p0,
                        previous_p0=previous_p0,
                        previous_r2=previous_r2,
                        user_p0=p0,
                        min_points=min_points,
                    )
                    popt, std_errors, r_squared, rmse = spec.fit_fn(
                        time_s, intensity, effective_p0
                    )
                    if (
                        model_key == "secondary_pfo"
                        and carry_forward_p0
                        and np.isfinite(r_squared)
                        and (
                            previous_r2 is None
                            or r_squared > previous_r2 + r2_improvement_threshold
                        )
                    ):
                        previous_p0 = (
                            list(effective_p0) if effective_p0 is not None else None
                        )
                        previous_r2 = float(r_squared)

                    record = {
                        "Peak_Name": str(current_row["Peak_Name"]),
                        "Time (s)": float(unique_time),
                        spec.r2_col: r_squared,
                        spec.rmse_col: rmse,
                        "classification": classification_value,
                        "growth_onset_s": breakpoint_used_value,
                    }

                    if (
                        peak_name == "cluster_sum"
                        and classification_value == "discontinuous"
                    ):
                        for key, value in classification.items():
                            if key.startswith("pre_") or key.startswith("post_"):
                                record[key] = value

                    for idx, (value_key, stderr_key) in enumerate(spec.param_map):
                        value = popt[idx] if idx < len(popt) else np.nan
                        record[value_key] = (
                            float(value) if np.isfinite(value) else np.nan
                        )
                        if stderr_key is not None:
                            stderr = (
                                std_errors[idx] if idx < len(std_errors) else np.nan
                            )
                            record[stderr_key] = (
                                float(stderr) if np.isfinite(stderr) else np.nan
                            )

                    records.append(record)

        return pd.DataFrame(records) if records else pd.DataFrame()

    def prepare_pfo_classification_rows(
        self,
        df: pd.DataFrame,
        *,
        min_points: int = 4,
        peak_names: list[str] | None = None,
        classify_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> pd.DataFrame:
        df = self.utils.prepare_peak_area_df(df)
        if peak_names is not None:
            df = cast(pd.DataFrame, df[df["Peak_Name"].isin(peak_names)].copy())

        records: list[dict[str, float | str]] = []
        for group_key, group_raw in df.groupby("Peak_Name"):
            group = cast(
                pd.DataFrame, group_raw.sort_values("Time (s)").reset_index(drop=True)
            )
            peak_name = str(group_key)

            classification_value, breakpoint_used_value, classification = (
                self._classification_payload(group, peak_name, min_points, classify_fn)
            )

            for idx in range(len(group)):
                current_row = group.iloc[idx]
                record: dict[str, float | str] = {
                    "Peak_Name": str(current_row["Peak_Name"]),
                    "Time (s)": float(current_row["Time (s)"]),
                    "classification": classification_value,
                    "growth_onset_s": breakpoint_used_value,
                }
                if (
                    peak_name == "cluster_sum"
                    and classification_value == "discontinuous"
                ):
                    for key, value in classification.items():
                        if key.startswith("pre_") or key.startswith("post_"):
                            record[key] = value
                records.append(record)

        return pd.DataFrame(records) if records else pd.DataFrame()

    def write_model_fit_params(
        self,
        model_key: str,
        carbonyl_peak_area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        min_points: int = 4,
        peak_names: list[str] | None = None,
        mode: str = "rolling",
        p0: list[float] | None = None,
        use_prior_p0: bool = True,
        monomer_sum_peaks: list[str] | None = None,
        cluster_sum_peaks: list[str] | None = None,
    ) -> Path:
        """Fit a single kinetics model to one CarbonylPeakArea CSV.

        Reads the CSV, fits the model, merges results back into the
        legacy data, and writes the output to ``output_folder_name``.

        Parameters
        ----------
        model_key : str
            Which model to fit: ``"pfo"`` or ``"secondary_pfo"``.
        carbonyl_peak_area_path : str | Path
            Path to the input ``*_CarbonylPeakArea.csv``.
        output_folder_name : str
            Subdirectory name for output CSVs (e.g. ``"_test"``).
        min_points : int
            Minimum number of time points required before fitting starts.
        peak_names : list[str] | None
            Restrict fitting to these peak names.  None = all peaks.
        mode : str
            ``"rolling"`` fits at every time point with an expanding window.
            ``"full_series"`` fits once using all data.
        p0 : list[float] | None
            User-supplied initial guess for the optimizer.  None = use
            built-in defaults.
        use_prior_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            ``p0`` (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        monomer_sum_peaks : list[str] | None
            Override which Peak_Name rows get summed into ``monomer_sum``.
            None = use the config-defined definition (or the input CSV's
            existing monomer_sum row, if already present).
        cluster_sum_peaks : list[str] | None
            Same override, for ``cluster_sum``.
        """
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df_legacy = pd.read_csv(carbonyl_peak_area_path)
        df_legacy = self.utils.prepare_peak_area_df(
            df_legacy,
            monomer_sum_peaks=monomer_sum_peaks,
            cluster_sum_peaks=cluster_sum_peaks,
        )

        fit_params = self._prepare_model_rows_for_file(
            model_key,
            df_legacy,
            min_points=min_points,
            peak_names=peak_names,
            mode=mode,
            p0=p0,
            carry_forward_p0=use_prior_p0,
        )
        if fit_params.empty:
            raise ValueError(f"No fit results were produced for model: {model_key}")
        return self.utils.write_fit_params_to_legacy(
            carbonyl_peak_area_path,
            fit_params,
            output_folder_name=output_folder_name,
            legacy_df=df_legacy,
        )

    def write_sum_model_fit_params(
        self,
        carbonyl_peak_area_path: str | Path,
        *,
        monomer_model_key: str = "secondary_pfo",
        cluster_model_key: str = "pfo",
        output_folder_name: str = "_test",
        min_points: int = 4,
        mode: str = "rolling",
        monomer_p0: list[float] | None = None,
        cluster_p0: list[float] | None = None,
        carry_forward_p0: bool = True,
    ) -> Path:
        """Fit monomer and cluster groups with separate model assignments.

        Monomer group uses config-based monomer peaks + ``monomer_sum``,
        fitted with ``monomer_model_key`` (default: ``secondary_pfo``).
        Cluster group uses config-based cluster peaks + ``cluster_sum``,
        fitted with ``cluster_model_key`` (default: ``pfo``).
        Results are merged into one legacy output CSV.

        Parameters
        ----------
        carbonyl_peak_area_path : str | Path
            Path to the input ``*_CarbonylPeakArea.csv``.
        monomer_model_key : str
            Model for monomer peaks (default ``"secondary_pfo"``).
        cluster_model_key : str
            Model for cluster peaks (default ``"pfo"``).
        output_folder_name : str
            Subdirectory name for output CSVs (e.g. ``"_test"``).
        min_points : int
            Minimum number of time points required before fitting starts.
        mode : str
            ``"rolling"`` fits at every time point with an expanding window.
            ``"full_series"`` fits once using all data.
        monomer_p0 : list[float] | None
            Initial guess for monomer model optimizer.  None = defaults.
        cluster_p0 : list[float] | None
            Initial guess for cluster model optimizer.  None = defaults.
        carry_forward_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            the user p0 (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        """
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df_legacy = pd.read_csv(carbonyl_peak_area_path)
        df_legacy = self.utils.prepare_peak_area_df(df_legacy)

        monomer_peak_names = [
            *self.utils.get_monomer_peak_names(isotope=None),
            "monomer_sum",
        ]
        cluster_peak_names = [
            *self.utils.get_peak_names("cluster_peaks_base", isotope=None),
            "cluster_sum",
        ]

        overlap = set(monomer_peak_names) & set(cluster_peak_names)
        if overlap:
            raise ValueError(
                "Monomer/cluster peak sets overlap in config: "
                + ", ".join(sorted(overlap))
            )

        monomer_rows = self._prepare_model_rows_for_file(
            monomer_model_key,
            df_legacy,
            min_points=min_points,
            peak_names=monomer_peak_names,
            mode=mode,
            p0=monomer_p0,
            carry_forward_p0=carry_forward_p0,
        )
        cluster_rows = self._prepare_model_rows_for_file(
            cluster_model_key,
            df_legacy,
            min_points=min_points,
            peak_names=cluster_peak_names,
            mode=mode,
            p0=cluster_p0,
            carry_forward_p0=carry_forward_p0,
        )

        frames = [frame for frame in [monomer_rows, cluster_rows] if not frame.empty]
        if not frames:
            raise ValueError("No fit results were produced for monomer/cluster groups.")

        fit_params = pd.concat(frames, ignore_index=True)
        return self.utils.write_fit_params_to_legacy(
            carbonyl_peak_area_path,
            fit_params,
            output_folder_name=output_folder_name,
            legacy_df=df_legacy,
        )

    def write_pfo_classification(
        self,
        carbonyl_peak_area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        min_points: int = 4,
        peak_names: list[str] | None = None,
        classify_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> Path:
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df_legacy = pd.read_csv(carbonyl_peak_area_path)
        df_legacy = self.utils.prepare_peak_area_df(df_legacy)
        fit_params = self.prepare_pfo_classification_rows(
            df_legacy,
            min_points=min_points,
            peak_names=peak_names,
            classify_fn=classify_fn,
        )
        if fit_params.empty:
            raise ValueError("No classification results were produced.")
        return self.utils.write_fit_params_to_legacy(
            carbonyl_peak_area_path,
            fit_params,
            output_folder_name=output_folder_name,
            legacy_df=df_legacy,
        )

    def remove_legacy_pfo_columns_file(
        self,
        carbonyl_peak_area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        prefixes: tuple[str, ...] = ("pfo",),
    ) -> Path:
        """Remove columns whose names start with any of ``prefixes`` from one CSV."""
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df = pd.read_csv(carbonyl_peak_area_path)
        cleaned_df, _dropped_columns = self.utils.drop_columns_with_prefixes(
            df, prefixes
        )
        return self.utils.write_plain_legacy_output(
            carbonyl_peak_area_path,
            cleaned_df,
            output_folder_name=output_folder_name,
        )


# --- Instances ---
UTILS = _KineticUtilities()
MODELS = KineticModels(UTILS)
CLASSIFIER = KineticClassification(MODELS, UTILS)
WRITER = KineticWriter(UTILS, MODELS, CLASSIFIER)
