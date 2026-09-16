"""Plot raw subIFG, its baseline, and the baseline-subtracted signal.

One figure per subIFG file, matching ``plot_individual_fit.py``'s unit.

When a run used ``baseline="recompute"`` the recomputed baseline is drawn
alongside the saved one. With no ``ir_fitting.baseline`` settings override the
two coincide exactly -- ``pybaselines.classification.std_distribution`` takes no
peak list, so declaring extra peaks cannot change it (spec.md section 6). That
coincidence is the check that nothing drifted; a visible gap means a settings
change actually moved the baseline.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[2]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting.result_types import FileFitResult, MeasurementFitResult
from src.visualizations._axes import rescale_y_to_window

LOGGER = logging.getLogger(__name__)

X_LIMITS = (2250, 1750)
ZOOM_LIMITS = (1900, 1750)
"""Low-wavenumber window where the two candidate bands live."""


def figure_dir(folder_name: str) -> Path:
    """Return the output directory for baseline figures."""
    return Path(
        config.get_path(
            "data.figures",
            folder_name,
            config.get_path("data.plot_baseline"),
        )
    )


def _saved_baseline_column(
    folder_name: str,
    file_name: str,
    file_key: str,
) -> np.ndarray | None:
    """Read one file's column from the dataset's saved baseline CSV."""
    suffix = str(config.get_setting("filenames.carbonyl_fit.baseline_suffix"))
    csv_path = Path(config.get_path("data.peak_fit", folder_name)) / (
        f"{file_name}{suffix}"
    )
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    if file_key not in df.columns:
        return None
    return np.asarray(pd.to_numeric(df[file_key], errors="coerce"), dtype=float)


def plot_file_baseline(
    result: FileFitResult,
    *,
    folder_name: str,
    file_name: str,
    compare_saved: bool = True,
    xlim: tuple[float, float] = X_LIMITS,
    save: bool = True,
    dpi: int = 300,
) -> Path | None:
    """Plot raw / baseline / subtracted for one subIFG file.

    Args:
        result: The per-file fit outcome.
        folder_name: Dataset folder, used to resolve paths.
        file_name: Measurement base name.
        compare_saved: When the run recomputed its baseline, overlay the saved
            one for comparison.
        xlim: Wavenumber range to display, high to low. Defaults to the full
            ROI; pass ``ZOOM_LIMITS`` for the low-wavenumber bands. The y axis
            is rescaled to whatever the window contains.
        save: Write the figure to disk.
        dpi: Figure resolution.

    Returns:
        The written path, or None when ``save`` is False.
    """
    x = result.wavenumbers

    fig, (ax_raw, ax_sub) = plt.subplots(
        2,
        1,
        figsize=(7, 6),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1]},
    )

    ax_raw.plot(x, result.raw, color="black", linewidth=1.0, label="raw subIFG")
    ax_raw.plot(
        x,
        result.baseline,
        color="tab:green",
        linewidth=1.2,
        label=f"baseline ({result.baseline_source})",
    )

    saved = None
    if compare_saved and result.baseline_source == "recompute":
        saved = _saved_baseline_column(folder_name, file_name, result.file_key)
        if saved is not None and saved.size == x.size:
            ax_raw.plot(
                x,
                saved,
                color="tab:purple",
                linewidth=1.0,
                linestyle="--",
                label="baseline (saved)",
            )

    ax_raw.set_ylabel("Log Reflectance")
    ax_raw.set_title(f"{file_name}  {result.file_key}", fontsize=9)
    ax_raw.legend(fontsize=7, loc="upper right")

    ax_sub.plot(
        x,
        result.corrected,
        color="black",
        linewidth=1.0,
        label=f"subtracted ({result.baseline_source})",
    )
    if saved is not None and saved.size == x.size:
        ax_sub.plot(
            x,
            result.raw - saved,
            color="tab:purple",
            linewidth=1.0,
            linestyle="--",
            label="subtracted (saved)",
        )
        max_gap = float(np.nanmax(np.abs(result.baseline - saved)))
        ax_sub.set_title(
            f"max |recompute - saved| = {max_gap:.2e}",
            fontsize=8,
        )
    ax_sub.axhline(0, color="0.7", linewidth=0.5)
    ax_sub.set_ylabel("Log Reflectance")
    ax_sub.set_xlabel("Wavenumber (cm-1)")
    ax_sub.set_xlim(xlim)
    ax_sub.legend(fontsize=7, loc="upper right")

    for axes in (ax_raw, ax_sub):
        rescale_y_to_window(axes, x, xlim)

    fig.tight_layout()

    if not save:
        return None

    output_dir = figure_dir(folder_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Keep zoomed figures from overwriting full-range ones.
    suffix = "" if tuple(xlim) == X_LIMITS else f"_{int(min(xlim))}-{int(max(xlim))}"
    output_path = output_dir / f"{file_name}_{result.file_key}{suffix}.png"
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_measurement_baselines(
    measurement: MeasurementFitResult,
    *,
    file_keys: list[str] | None = None,
    compare_saved: bool = True,
    xlim: tuple[float, float] = X_LIMITS,
    save: bool = True,
    dpi: int = 300,
) -> list[Path]:
    """Plot baselines for every file in a measurement.

    ``file_keys`` restricts output to specific files (e.g. ``["delta5.0007"]``).
    """
    written: list[Path] = []
    for result in measurement.files:
        if file_keys is not None and result.file_key not in file_keys:
            continue
        output_path = plot_file_baseline(
            result,
            folder_name=measurement.folder_name,
            file_name=measurement.file_name,
            compare_saved=compare_saved,
            xlim=xlim,
            save=save,
            dpi=dpi,
        )
        if output_path is not None:
            written.append(output_path)
    LOGGER.info("Wrote %d baseline figures", len(written))
    return written


def plot_baselines(
    folder_name: str,
    name: str,
    *,
    file_keys: list[str] | None = None,
    xlim: tuple[float, float] = ZOOM_LIMITS,
    baseline: str = "saved",
    compare_saved: bool = True,
    save: bool = True,
    dpi: int = 300,
) -> list[Path]:
    """Plot the saved baselines for one measurement. Fits nothing.

    The entry point for looking at baselines:

        plot_baselines("nn1120-3_pd_ceo2_004", "20260304_145524_pd_ceo2_004-000")

    Loads the measurement via :func:`~src.utils.ir_fitting.load_measurement`, so
    it does **not** depend on ``ir_fitting.extra_peaks_base`` and writes nothing
    to the peak-fit folder -- only figures. Defaults to the low-wavenumber window
    where the candidate bands live; pass ``xlim=X_LIMITS`` for the full ROI.

    Args:
        folder_name: Dataset folder, e.g. ``"nn1120-3_pd_ceo2_004"``.
        name: Measurement base name, e.g.
            ``"20260304_145524_pd_ceo2_004-000"``.
        file_keys: Restrict to specific files (e.g. ``["delta5.0007"]``).
            ``None`` plots every file in the measurement.
        xlim: Wavenumber range, high to low. y is rescaled to it.
        baseline: ``"saved"`` or ``"recompute"``.
        compare_saved: Overlay the saved baseline when recomputing.
        save: Write figures to disk.
        dpi: Figure resolution.

    Returns:
        Paths of the figures written.
    """
    from src.utils.ir_fitting import load_measurement, subifg_dir

    measurement = load_measurement(subifg_dir(folder_name) / name, baseline=baseline)
    return plot_measurement_baselines(
        measurement,
        file_keys=file_keys,
        compare_saved=compare_saved,
        xlim=xlim,
        save=save,
        dpi=dpi,
    )


if __name__ == "__main__":
    # Edit these constants to run a batch.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")

    folder_name = "nn1120-3_pd_ceo2_004"
    name = "20260304_145524_pd_ceo2_004-000"

    # No fitting, no dependency on ir_fitting.extra_peaks_base.
    # Drop file_keys to plot every file; pass xlim=X_LIMITS for the full ROI.
    paths = plot_baselines(folder_name, name, file_keys=["delta5.0007"])
    for item in paths:
        print(item)
