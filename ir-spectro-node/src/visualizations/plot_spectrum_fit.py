"""Plot spectral fit outputs for visual inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import sys
from typing import cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import voigt_profile

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import get_shifted_monomer_peaks
from src.core import config


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpectrumFitPaths:
    folder_name: str
    file_name: str
    base_name: str

    @property
    def fit_params_dir(self) -> Path:
        return Path(config.get_path("data.peak_fit", self.folder_name))

    @property
    def _params_suffix(self) -> str:
        return cast(str, config.get_setting("filenames.carbonyl_fit.params_suffix"))

    @property
    def _baseline_suffix(self) -> str:
        return cast(str, config.get_setting("filenames.carbonyl_fit.baseline_suffix"))

    @property
    def _residual_suffix(self) -> str:
        return cast(str, config.get_setting("filenames.carbonyl_fit.residual_suffix"))

    @property
    def file_stem(self) -> str:
        if self.file_name.endswith(self._params_suffix):
            return self.file_name[: -len(self._params_suffix)]
        return Path(self.file_name).stem

    @property
    def baseline_csv(self) -> Path:
        return self.fit_params_dir / f"{self.file_stem}{self._baseline_suffix}"

    @property
    def residual_csv(self) -> Path:
        return self.fit_params_dir / f"{self.file_stem}{self._residual_suffix}"

    @property
    def params_csv(self) -> Path:
        return self.fit_params_dir / f"{self.file_stem}{self._params_suffix}"

    @property
    def subifg_dir(self) -> Path:
        return Path(
            config.get_path("utility.subtract_ifg.sub_ifg_output", self.folder_name)
        )

    @property
    def figure_dir(self) -> Path:
        return Path(
            config.get_path(
                "data.figures",
                self.folder_name,
                config.get_path("data.plot_spectrum_fit"),
            )
        )


def _voigt_model(
    x: np.ndarray,
    y0: float,
    amplitude: float,
    center: float,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))


def _log_shape_details(label: str, array: np.ndarray) -> None:
    LOGGER.info("%s shape=%s dtype=%s", label, array.shape, array.dtype)


def _load_fit_tables(
    paths: SpectrumFitPaths,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    if not paths.params_csv.exists():
        LOGGER.warning("Missing fit params: %s", paths.params_csv)
        return None
    if not paths.baseline_csv.exists():
        LOGGER.warning("Missing baseline: %s", paths.baseline_csv)
        return None
    if not paths.residual_csv.exists():
        LOGGER.warning("Missing residual: %s", paths.residual_csv)
        return None

    try:
        df_fit_params = pd.read_csv(paths.params_csv)
        df_baseline = pd.read_csv(paths.baseline_csv)
        df_residual = pd.read_csv(paths.residual_csv)
    except Exception as exc:
        LOGGER.error("Error reading fit tables: %s", exc)
        return None
    return df_fit_params, df_baseline, df_residual


def _build_x_axis(df_baseline: pd.DataFrame) -> tuple[np.ndarray, tuple[float, float]]:
    arr_baseline = df_baseline.values
    x_start = round(arr_baseline[0, 0], 4)
    x_end = round(arr_baseline[-1, 0], 4)
    x = np.linspace(x_start, x_end, arr_baseline[:, 0].size)
    # _log_shape_details("baseline array", arr_baseline)
    LOGGER.info("x range=%s..%s size=%s", x_start, x_end, x.size)
    return x, (x_start, x_end)


def _collect_delta_groups(paths: SpectrumFitPaths) -> dict[str, list[Path]]:
    delta_groups: dict[str, list[Path]] = {}
    for file in sorted(paths.subifg_dir.glob(f"{paths.file_stem}*")):
        delta_file = file.stem.split("_")[-1]
        if delta_file not in {
            "delta1",
            "delta5",
            "delta6",
            "delta7",
            "delta8",
            "delta9",
            "delta10",
        }:
            continue
        delta_groups.setdefault(delta_file, []).append(file)
    return delta_groups


def _filter_subifg_spectrum(
    df: pd.DataFrame, x_limits: tuple[float, float]
) -> np.ndarray:
    upper, lower = max(x_limits), min(x_limits)
    mask = (df[0].round(4) >= lower) & (df[0].round(4) <= upper)
    filtered = df.loc[mask, 1].to_numpy()
    if filtered.size == 0:
        LOGGER.warning("Filtered spectrum is empty (limits=%s)", x_limits)
    return filtered


def _sum_delta_group_data(
    delta_groups: dict[str, list[Path]],
    df_baseline: pd.DataFrame,
    df_residual: pd.DataFrame,
    x: np.ndarray,
    x_limits: tuple[float, float],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    delta_group_data: dict[str, np.ndarray] = {}
    delta_group_residual: dict[str, np.ndarray] = {}

    for delta_file, files in delta_groups.items():
        arr_subifg = np.zeros_like(x)
        arr_residual = np.zeros_like(x)
        for file in files:
            iterator = file.suffix.lstrip(".")
            if _manually_skip_files(delta_file, iterator):
                continue
            key = f"{delta_file}.{iterator}"
            if key not in df_baseline.columns or key not in df_residual.columns:
                message = f"Missing baseline/residual column: {key} ({file})"
                LOGGER.warning(message)
                continue

            arr_baseline = df_baseline[key].to_numpy()
            arr_residual_col = df_residual[key].to_numpy()
            df_subifg = pd.read_csv(file, header=None)
            arr_sub = _filter_subifg_spectrum(df_subifg, x_limits)

            LOGGER.info(
                "%s baseline=%s residual=%s subifg=%s",
                key,
                arr_baseline.shape,
                arr_residual_col.shape,
                arr_sub.shape,
            )

            if arr_sub.shape != arr_baseline.shape:
                message = (
                    f"Shape mismatch for {key} ({file}): subifg={arr_sub.shape} "
                    f"baseline={arr_baseline.shape}"
                )
                LOGGER.warning(message)
                continue

            if arr_residual_col.shape != arr_baseline.shape:
                message = (
                    f"Residual shape mismatch for {key} ({file}): residual={arr_residual_col.shape} "
                    f"baseline={arr_baseline.shape}"
                )
                LOGGER.warning(message)
                continue

            arr_subifg += arr_sub - arr_baseline
            arr_residual += arr_residual_col

        delta_group_data[delta_file] = arr_subifg
        delta_group_residual[delta_file] = arr_residual

    return delta_group_data, delta_group_residual


def _manually_skip_files(delta_file: str, file_index: str) -> bool:
    if (delta_file == "delta1") and (int(file_index) > 2):
        return True
    if delta_file in {"delta2", "delta3", "delta4"}:
        return True
    return False


def _build_delta_group_fit(
    df_fit_params: pd.DataFrame, x: np.ndarray
) -> dict[str, np.ndarray]:
    delta_group_fit: dict[str, np.ndarray] = {}
    df_fit_params = df_fit_params.dropna(
        subset=["Y0", "Amplitude", "Center", "Sigma", "Gamma"]
    )
    for delta_group, group in df_fit_params.groupby("Delta_Group"):
        y = np.zeros_like(x)
        for _, row in group.iterrows():
            y += _voigt_model(
                x,
                float(row["Y0"]),
                float(row["Amplitude"]),
                float(row["Center"]),
                float(row["Sigma"]),
                float(row["Gamma"]),
            )
        delta_group_fit[str(delta_group)] = y
    return delta_group_fit


def _build_peak_fits(
    df_fit_params: pd.DataFrame, x: np.ndarray
) -> dict[str, dict[str, np.ndarray]]:
    peaks_data: dict[str, dict[str, np.ndarray]] = {}
    for group_keys, group in df_fit_params.groupby(["Delta_Group", "Peak_Name"]):
        delta_group, peak_name = cast(tuple[object, object], group_keys)
        delta_key = str(delta_group)
        peak_key = str(peak_name)
        peaks_data.setdefault(delta_key, {})
        y = np.zeros_like(x)
        for _, row in group.iterrows():
            y += _voigt_model(
                x,
                float(row["Y0"]),
                float(row["Amplitude"]),
                float(row["Center"]),
                float(row["Sigma"]),
                float(row["Gamma"]),
            )
        peaks_data[delta_key][peak_key] = y
    return peaks_data


def _get_monomer_peaks(isotope: str | None) -> list[float]:
    config_settings = config.get_analysis_setting("voigt_fit")
    isotope_value = isotope or config_settings.get("isotope_default", "13CO")
    merged_settings = dict(config_settings)
    merged_settings["isotope_default"] = isotope_value
    return get_shifted_monomer_peaks(merged_settings)


def plot_spectrum_fit(
    file_path: str,
    isotope: str | None = None,
    plot_individual_peaks: bool = False,
) -> None:
    file_path_obj = Path(file_path)
    paths = SpectrumFitPaths(
        folder_name=file_path_obj.parents[0].name,
        file_name=file_path_obj.name,
        base_name=("_").join(file_path_obj.name.split("_")),
    )

    tables = _load_fit_tables(paths)
    if tables is None:
        return

    df_fit_params, df_baseline, df_residual = tables
    x, x_limits = _build_x_axis(df_baseline)

    delta_groups = _collect_delta_groups(paths)
    if not delta_groups:
        LOGGER.warning("No delta groups found for %s", paths.file_name)
        return

    delta_group_data, delta_group_residual = _sum_delta_group_data(
        delta_groups,
        df_baseline,
        df_residual,
        x,
        x_limits,
    )
    delta_group_fit = _build_delta_group_fit(df_fit_params, x)
    peaks_data = _build_peak_fits(df_fit_params, x) if plot_individual_peaks else {}
    peaks = [f"Peak_{int(peak)}" for peak in _get_monomer_peaks(isotope)]
    for delta_group, arr in delta_group_data.items():
        if delta_group == "delta1":
            continue
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.plot(x, arr, linestyle="-", color="black", label=f"{delta_group} data")
        if delta_group in delta_group_fit:
            ax.plot(
                x,
                delta_group_fit[delta_group],
                linestyle="-",
                color="red",
                linewidth=1,
                label=f"{delta_group} fit",
            )
        if delta_group in delta_group_residual:
            ax.plot(
                x,
                delta_group_residual[delta_group],
                linestyle="-",
                color="blue",
                linewidth=1,
                label=f"{delta_group} residual",
            )
        if plot_individual_peaks:
            for peak in peaks:
                if delta_group in peaks_data and peak in peaks_data[delta_group]:
                    ax.plot(
                        x,
                        peaks_data[delta_group][peak],
                        linestyle="--",
                        linewidth=1,
                        label=peak,
                    )

        ax.set_xlabel("Wavenumber (cm-1)")
        ax.set_ylabel("Log Reflectance")
        ax.legend(loc="upper right", bbox_to_anchor=(1, 1))
        ax.invert_xaxis()
        ax.set_xlim((2250, 1750))

        paths.figure_dir.mkdir(parents=True, exist_ok=True)
        output_path = paths.figure_dir / f"{paths.base_name}_{delta_group}.tiff"
        plt.savefig(output_path, dpi=800, bbox_inches="tight")
        plt.close(fig)


def process_all_plot_spectrum_fit(
    folder: str,
    *,
    isotope: str | None = None,
    plot_individual_peaks: bool = False,
) -> None:
    file_directory = Path(
        config.get_path("utility.subtract_ifg.sub_ifg_output", folder)
    )
    figure_directory = Path(
        config.get_path(
            "data.figures",
            folder,
            config.get_path("data.plot_spectrum_fit"),
        )
    )
    figure_directory.mkdir(parents=True, exist_ok=True)

    unique_names: set[str] = set()
    for file_path in file_directory.iterdir():
        if file_path.is_file():
            base_name = "_".join(file_path.name.split("_")[:-1])
            if base_name:
                unique_names.add(base_name)

    for base_name in sorted(unique_names):
        plot_spectrum_fit(
            str(file_directory / base_name),
            isotope=isotope,
            plot_individual_peaks=plot_individual_peaks,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    process_all_plot_spectrum_fit("nn1120-3_pd_ceo2_004")
    # plot_spectrum_fit(
    #     r"C:\\Data\\OpusConvert_subIFG_lgRfl\\nn1120-3_pd_ceo2_004\\20260312_160922_pd_ceo2_004-005",
    # )
