#!/usr/bin/env python3
"""Plot kinetics fit parameters across dataset folders."""

from __future__ import annotations

from pathlib import Path
import logging
import sys
from typing import cast, Literal

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config


LOGGER = logging.getLogger(__name__)

DEFAULT_DATASET_FOLDERS = ["nn1120-3_pd_ceo2_004"]
DEFAULT_SCAN_PARENT = False
DEFAULT_PEAK_NAMES = ["monomer_sum", "cluster_sum"]
DEFAULT_PFO_PARAMETERS = [
    "pfo_k_s-1",
    "pfo_q_e_au",
    "pfo_q0_au",
    "pfo_r^2",
    "pfo_rmse",
]
DEFAULT_SECONDARY_PFO_PARAMETERS = [
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
    "pfo-sec_r^2",
    "pfo-sec_rmse",
]
DEFAULT_DELTA_GROUP: str | None = None
DEFAULT_SHOW = False
DEFAULT_STDDEV_THRESHOLD: float | None = None  # Disable filtering by stddev for now
DEFAULT_MODEL: Literal["pfo", "secondary"] = "secondary"
PARENT_OUTPUT_SUBDIR = "plot_params_all"


def _resolve_output_path(
    output_dir: Path, base_name: str, peak_name: str, parameter: str, model: str = ""
) -> Path:
    safe_base = base_name.replace(" ", "_")
    safe_peak = peak_name.replace(" ", "_")
    safe_param = parameter.replace(" ", "_")
    model_suffix = f"_{model}" if model else ""
    return output_dir / f"{safe_base}_{safe_peak}_{safe_param}{model_suffix}.tiff"


def _resolve_dataset_paths(
    *, dataset_folders: list[str], scan_parent: bool | None = None
) -> list[Path]:
    data_root = Path(config.get_path("data.peak_fit"))
    scan_parent = DEFAULT_SCAN_PARENT if scan_parent is None else scan_parent
    if scan_parent:
        candidates = [
            path
            for path in data_root.iterdir()
            if path.is_dir()
            and "_test" not in path.name
            and "arxiv" not in path.name
            and "CalibrationData" not in path.name
        ]
        return sorted(candidates)

    return [data_root / folder for folder in dataset_folders]


def _extract_experiment_number(file_value: str, fallback: int) -> int:
    parts = file_value.split("-")
    if parts:
        last = parts[-1].split(".")[0]
        if last.isdigit():
            return int(last)
    return fallback


def _extract_parameter_value(
    df: pd.DataFrame,
    parameter: str,
    *,
    delta_group: str | None,
    model: Literal["pfo", "secondary"] = "pfo",
) -> float | None:
    df = df.copy()
    if "Time (s)" not in df.columns:
        return None
    if delta_group and "Delta_Group" in df.columns:
        df = df.loc[df["Delta_Group"] == delta_group].copy()
    if df.empty:
        return None

    parameter_column = parameter
    if parameter_column not in df.columns or bool(df[parameter_column].isna().all()):
        return None

    # Define base params based on model
    if model == "secondary":
        base_params = {
            "pfo-sec_k_a_s-1",
            "pfo-sec_q_e_au",
            "pfo-sec_k_s_s-1",
            "pfo-sec_k_p_s-1",
            "pfo-sec_q_inf_au",
            "pfo-sec_q0_au",
        }
    else:
        base_params = {
            "pfo_k_s-1",
            "pfo_q_e_au",
            "pfo_q0_au",
        }
    pre_column = f"pre_{parameter}"

    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df[parameter_column] = pd.to_numeric(df[parameter_column], errors="coerce")
    df = df.dropna(subset=["Time (s)", parameter_column])
    if "r^2" in parameter_column:
        df = df.loc[(df[parameter_column] >= 0) & (df[parameter_column] <= 1)].copy()
    if df.empty:
        return None

    df = df.sort_values("Time (s)")
    if "Delta_Group" in df.columns and delta_group is None:
        last_rows = df.groupby("Delta_Group").tail(1)
        if (
            parameter in base_params
            and pre_column in last_rows.columns
            and "classification" in last_rows.columns
        ):
            values = last_rows[parameter_column].copy()
            use_pre = last_rows["classification"].astype(str) == "discontinuous"
            values.loc[use_pre] = last_rows.loc[use_pre, pre_column]
            values = pd.to_numeric(values, errors="coerce")
        else:
            values = pd.to_numeric(last_rows[parameter_column], errors="coerce")
        if not isinstance(values, pd.Series):
            return None
        values_array = values.to_numpy(dtype=float)
        values_array = values_array[np.isfinite(values_array)]
        if values_array.size == 0:
            return None
        return float(np.mean(values_array))
    if (
        parameter in base_params
        and pre_column in df.columns
        and "classification" in df.columns
        and str(df["classification"].iloc[-1]) == "discontinuous"
    ):
        pre_value = pd.to_numeric(df[pre_column].iloc[-1], errors="coerce")
        if isinstance(pre_value, float) and np.isfinite(pre_value):
            return float(pre_value)

    return float(df[parameter_column].iloc[-1])


def _collect_csv_paths(dataset_path: Path) -> list[Path]:
    suffix = cast(str, config.get_setting("filenames.carbonyl_fit.area_suffix"))
    csv_paths = sorted(dataset_path.glob(f"*{suffix}"))
    return [csv_path for csv_path in csv_paths if "arxiv" not in csv_path.parts]


def _filter_by_stddev(
    experiment_numbers: list[int],
    parameter_values: list[float],
    reference_flags: list[bool | None],
    *,
    threshold: float | None,
) -> tuple[list[int], list[float], list[bool | None]]:
    if threshold is None or len(parameter_values) < 2:
        return experiment_numbers, parameter_values, reference_flags

    values = np.array(parameter_values, dtype=float)
    mean_value = float(np.mean(values))
    std_value = float(np.std(values))
    if std_value == 0:
        return experiment_numbers, parameter_values, reference_flags

    mask = np.abs(values - mean_value) <= threshold * std_value
    filtered_experiments = [x for x, keep in zip(experiment_numbers, mask) if keep]
    filtered_values = [y for y, keep in zip(parameter_values, mask) if keep]
    filtered_flags = [flag for flag, keep in zip(reference_flags, mask) if keep]
    return filtered_experiments, filtered_values, filtered_flags


def _collect_parameter_points(
    csv_paths: list[Path],
    peak_name: str,
    parameter: str,
    *,
    delta_group: str | None,
    model: Literal["pfo", "secondary"] = "pfo",
) -> tuple[list[int], list[float], list[bool | None]]:
    experiment_numbers: list[int] = []
    parameter_values: list[float] = []
    reference_flags: list[bool | None] = []
    for index, csv_path in enumerate(csv_paths):
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            LOGGER.warning("Error reading %s: %s", csv_path, exc)
            continue
        if "Peak_Name" not in df.columns:
            continue
        df_peak = df.loc[df["Peak_Name"] == peak_name].copy()
        if df_peak.empty:
            continue
        param_value = _extract_parameter_value(
            df_peak,
            parameter,
            delta_group=delta_group,
            model=model,
        )
        if param_value is None:
            continue
        area_suffix = cast(
            str, config.get_setting("filenames.carbonyl_fit.area_suffix")
        )
        file_value = csv_path.name
        if csv_path.name.endswith(area_suffix):
            file_value = csv_path.name.replace(area_suffix, "")
        experiment_number = _extract_experiment_number(file_value, index + 1)
        experiment_numbers.append(experiment_number)
        parameter_values.append(param_value)
        exp_params_name = csv_path.name.replace(area_suffix, "_expParams.csv")
        exp_params_path = (
            Path(config.get_path("data.exp_params"))
            / csv_path.parent.name
            / exp_params_name
        )
        reference_flags.append(_read_is_reference(exp_params_path))

    if not experiment_numbers:
        return experiment_numbers, parameter_values, reference_flags

    return _filter_by_stddev(
        experiment_numbers,
        parameter_values,
        reference_flags,
        threshold=DEFAULT_STDDEV_THRESHOLD,
    )


def _parse_reference_value(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, (pd.Series, pd.DataFrame, np.ndarray, list, tuple)):
        return None
    is_null = pd.isna(value)
    if isinstance(is_null, (np.bool_, bool)) and bool(is_null):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        if np.isfinite(value):
            return bool(int(value))
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _read_is_reference(exp_params_path: Path) -> bool | None:
    if not exp_params_path.exists():
        LOGGER.debug("Missing exp params: %s", exp_params_path)
        return None
    try:
        df = pd.read_csv(exp_params_path)
    except Exception as exc:
        LOGGER.debug("Failed to read exp params: %s (%s)", exp_params_path, exc)
        return None
    if "is_reference" not in df.columns or df.empty:
        return None
    return _parse_reference_value(df["is_reference"].iloc[0])


def plot_parameter_by_experiment(
    dataset_paths: list[Path],
    peak_names: list[str],
    parameters: list[str],
    output_dir: Path,
    base_name: str,
    *,
    delta_group: str | None,
    model: Literal["pfo", "secondary"] = "pfo",
) -> None:
    """Plot parameter values versus experiment number for each peak name."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for parameter in parameters:
        for peak_name in peak_names:
            plt.figure(figsize=(8, 5))
            has_reference_label = False
            has_measure_label = False
            parameter_values: list[float] = []
            all_values: list[float] = []
            index_offset = 0
            for dataset_path in dataset_paths:
                csv_paths = _collect_csv_paths(dataset_path)
                if not csv_paths:
                    continue
                (
                    _experiment_numbers,
                    parameter_values,
                    reference_flags,
                ) = _collect_parameter_points(
                    csv_paths,
                    peak_name,
                    parameter,
                    delta_group=delta_group,
                    model=model,
                )
                if not parameter_values:
                    continue
                all_values.extend(parameter_values)
                x_values = list(
                    range(index_offset, index_offset + len(parameter_values))
                )
                index_offset += len(parameter_values)
                ref_x: list[int] = []
                ref_y: list[float] = []
                meas_x: list[int] = []
                meas_y: list[float] = []
                for x_value, y_value, is_reference in zip(
                    x_values, parameter_values, reference_flags
                ):
                    if is_reference:
                        ref_x.append(x_value)
                        ref_y.append(y_value)
                    else:
                        meas_x.append(x_value)
                        meas_y.append(y_value)

                if ref_x:
                    plt.scatter(
                        ref_x,
                        ref_y,
                        color="blue",
                        label=None if has_reference_label else "reference",
                    )
                    has_reference_label = True
                if meas_x:
                    plt.scatter(
                        meas_x,
                        meas_y,
                        color="red",
                        label=None if has_measure_label else "measurement",
                    )
                    has_measure_label = True

            if plt.gca().has_data() and all_values:
                plt.xlabel("Index")
                plt.ylabel(parameter)
                positive_values = [value for value in all_values if value > 0]
                # use_log = "k" in parameter and len(positive_values) == len(all_values)
                # plt.yscale("log" if use_log else "linear")
                # if use_log:
                #     y_max = max(positive_values) * 1.02
                #     y_min = min(positive_values) * 0.98
                # else:
                #     y_max = max(all_values) * 1.02
                #     # y_min = -0.02
                # plt.ylim(top=y_max)
                # # Add secondary-specific y-limits
                # # if parameter in {"pfo_qe_au"}:
                # #     plt.ylim(bottom=-0.02, top=2)
                plt.title(f"{peak_name}: {parameter}")
                plt.legend(fontsize=8, loc="best")
                plt.tight_layout()
                output_path = _resolve_output_path(
                    output_dir, base_name, peak_name, parameter, model=model
                )
                plt.savefig(output_path, dpi=300)
                if DEFAULT_SHOW:
                    plt.show()
                else:
                    plt.close()
            else:
                plt.close()


def plot_params_folder(
    file_path: str | Path,
    *,
    peak_names: list[str] | None = None,
    parameters: list[str] | None = None,
    delta_group: str | None = DEFAULT_DELTA_GROUP,
    model: Literal["pfo", "secondary"] = "pfo",
) -> None:
    """Plot parameter trends for a single folder."""
    file_path_obj = Path(file_path)
    data_root = Path(config.get_path("data.peak_fit"))
    area_suffix = cast(str, config.get_setting("filenames.carbonyl_fit.area_suffix"))

    if file_path_obj.name.endswith(area_suffix):
        csv_path = (
            file_path_obj if file_path_obj.is_absolute() else data_root / file_path_obj
        )
        base_name = csv_path.stem.replace(area_suffix.replace(".csv", ""), "")
    else:
        if file_path_obj.is_absolute():
            LOGGER.warning("Unsupported absolute path for plot params: %s", file_path)
            return
        base_name = file_path_obj.stem if file_path_obj.suffix else file_path_obj.name
        relative_parent = file_path_obj.parent
        folder_root = data_root / relative_parent
        csv_path = folder_root / f"{base_name}{area_suffix}"

    try:
        dataset_folder = str(csv_path.parent.relative_to(data_root))
    except ValueError:
        dataset_folder = csv_path.parent.name

    if not csv_path.exists():
        LOGGER.warning("Missing carbonyl peak area CSV: %s", csv_path)
        return

    figure_dir = Path(
        config.get_path(
            "data.figures",
            dataset_folder,
            config.get_path("data.plot_params"),
        )
    )

    # Select parameters based on model
    if parameters is None:
        parameters = (
            DEFAULT_SECONDARY_PFO_PARAMETERS
            if model == "secondary"
            else DEFAULT_PFO_PARAMETERS
        )

    plot_parameter_by_experiment(
        [csv_path.parent],
        peak_names or DEFAULT_PEAK_NAMES,
        parameters,
        figure_dir,
        base_name,
        delta_group=delta_group,
        model=model,
    )


def plot_params_all(
    folder: str,
    *,
    peak_names: list[str] | None = None,
    parameters: list[str] | None = None,
    delta_group: str | None = DEFAULT_DELTA_GROUP,
    model: Literal["pfo", "secondary"] = "pfo",
) -> None:
    """Plot parameter trends for every peak-area CSV in a dataset folder."""
    dataset_paths = _resolve_dataset_paths(dataset_folders=[folder])
    if not dataset_paths:
        LOGGER.warning("No dataset folders found to plot.")
        return

    output_dir = Path(
        config.get_path(
            "data.figures",
            config.get_path("data.plot_params_all"),
        )
    )

    # Select parameters based on model
    if parameters is None:
        parameters = (
            DEFAULT_SECONDARY_PFO_PARAMETERS
            if model == "secondary"
            else DEFAULT_PFO_PARAMETERS
        )

    plot_parameter_by_experiment(
        dataset_paths,
        peak_names or DEFAULT_PEAK_NAMES,
        parameters,
        output_dir,
        folder,
        delta_group=delta_group,
        model=model,
    )


def main(
    model: Literal["pfo", "secondary"] = DEFAULT_MODEL,
) -> None:
    """CLI entry point for plotting parameter trends."""
    dataset_paths = _resolve_dataset_paths(
        dataset_folders=DEFAULT_DATASET_FOLDERS, scan_parent=DEFAULT_SCAN_PARENT
    )
    if not dataset_paths:
        raise SystemExit("No dataset folders found to plot.")

    if DEFAULT_SCAN_PARENT:
        dataset_label = "parent"
        output_dir = Path(config.get_path("data.figures")) / PARENT_OUTPUT_SUBDIR
    else:
        dataset_label = dataset_paths[0].name
        output_dir = Path(
            config.get_path(
                "data.figures",
                dataset_label,
                config.get_path("data.plot_params"),
            )
        )

    # Select parameters based on model
    parameters = (
        DEFAULT_SECONDARY_PFO_PARAMETERS
        if model == "secondary"
        else DEFAULT_PFO_PARAMETERS
    )

    plot_parameter_by_experiment(
        dataset_paths,
        DEFAULT_PEAK_NAMES,
        parameters,
        output_dir,
        dataset_label,
        delta_group=DEFAULT_DELTA_GROUP,
        model=model,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
    # plot_params_parent()
