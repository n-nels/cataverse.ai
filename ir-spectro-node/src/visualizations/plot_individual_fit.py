"""Plot one figure per subIFG file: data, composite fit, every peak, residual.

Deliberately not an extension of ``plot_spectrum_fit.py``: that module sums
every file within a delta group into a single trace and draws individual curves
only for monomer peaks. This one keeps each file separate and draws every peak,
which is what inspecting an individual fit needs.

Consumes a ``FileFitResult`` / ``MeasurementFitResult`` from
``src.utils.ir_fitting`` directly, so an EDA session can fit and plot without a
round trip through disk.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

path = Path(__file__).resolve().parents[2]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting.result_types import FileFitResult, MeasurementFitResult
from src.visualizations._axes import XLim, as_windows, rescale_y_to_window

LOGGER = logging.getLogger(__name__)

X_LIMITS = (2250, 1750)
ZOOM_LIMITS = (1900, 1750)
"""Low-wavenumber window where the two candidate bands live."""

DEFAULT_WINDOWS = (ZOOM_LIMITS, X_LIMITS)
"""Emit a zoomed and a full-range figure per file unless told otherwise."""

LIVE_PEAK_COLOR = "0.55"
NEW_PEAK_COLOR = "tab:orange"


def figure_dir(folder_name: str) -> Path:
    """Return the output directory for individual-fit figures."""
    return Path(
        config.get_path(
            "data.figures",
            folder_name,
            config.get_path("data.plot_individual_fit"),
        )
    )


def plot_file_fit(
    result: FileFitResult,
    *,
    folder_name: str,
    file_name: str,
    stacked: bool = False,
    residual_offset: bool = True,
    xlim: tuple[float, float] = X_LIMITS,
    save: bool = True,
    dpi: int = 300,
) -> Path | None:
    """Plot one subIFG file's fit.

    Args:
        result: The per-file fit outcome.
        folder_name: Dataset folder, used to resolve the figure directory.
        file_name: Measurement base name, used in the figure filename.
        stacked: Draw residual in its own panel sharing the x axis instead of
            offset below the data.
        residual_offset: When not stacked, offset the residual below the data so
            both stay readable at their own amplitudes.
        xlim: Wavenumber range to display, high to low. Defaults to the full
            ROI; pass ``ZOOM_LIMITS`` for the low-wavenumber bands. The y axis
            is rescaled to whatever the window contains.
        save: Write the figure to disk. When False the figure is rendered,
            closed, and no path is returned.
        dpi: Figure resolution.

    Returns:
        The written path, or None when ``save`` is False.
    """
    x = result.wavenumbers

    if stacked:
        fig, (ax, ax_residual) = plt.subplots(
            2,
            1,
            figsize=(7, 6),
            sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
        )
    else:
        fig, ax = plt.subplots(figsize=(7, 5))
        ax_residual = ax

    ax.plot(x, result.corrected, color="black", linewidth=1.2, label="data", zorder=3)
    ax.plot(x, result.composite, color="red", linewidth=1.1, label="fit", zorder=4)

    for curve in result.curves:
        is_new = curve.is_new
        ax.plot(
            x,
            curve.curve,
            linestyle="--",
            linewidth=1.1 if is_new else 0.7,
            color=NEW_PEAK_COLOR if is_new else LIVE_PEAK_COLOR,
            alpha=1.0 if is_new else 0.65,
            label=f"{curve.peak_name} (new)" if is_new else curve.peak_name,
            zorder=2,
        )

    residual = result.residual
    lower, upper = min(xlim), max(xlim)
    window = (x >= lower) & (x <= upper)
    offset = 0.0
    if not stacked and residual_offset:
        # Park the residual below the data rather than overlapping it. Measured
        # over the visible window so a zoom does not push it off-figure.
        offset = float(np.nanmin(result.corrected[window])) - 1.5 * float(
            np.nanmax(np.abs(residual[window]))
        )
    ax_residual.plot(
        x,
        residual + offset,
        color="tab:blue",
        linewidth=0.9,
        label="residual (model - data)",
        zorder=1,
    )
    if not stacked and residual_offset:
        ax_residual.axhline(offset, color="tab:blue", linewidth=0.5, alpha=0.4)

    ax.set_ylabel("Log Reflectance")
    ax.set_xlim(xlim)
    ax.set_title(f"{file_name}  {result.file_key}", fontsize=9)

    if stacked:
        ax_residual.set_ylabel("Residual")
        ax_residual.axhline(0, color="0.7", linewidth=0.5)
        ax_residual.set_xlabel("Wavenumber (cm-1)")
        ax_residual.set_xlim(xlim)
    else:
        ax.set_xlabel("Wavenumber (cm-1)")

    # When not stacked the two names are the same axes object.
    for axes in [ax] if ax_residual is ax else [ax, ax_residual]:
        rescale_y_to_window(axes, x, xlim)

    handles, labels = ax.get_legend_handles_labels()
    if not stacked:
        extra = ax_residual.get_legend_handles_labels()
        handles, labels = handles + extra[0][-1:], labels + extra[1][-1:]
    ax.legend(handles, labels, fontsize=6, ncol=2, loc="upper right")
    fig.tight_layout()

    if not save:
        # Close even when not writing: a measurement holds dozens of files, and
        # returning None leaves the caller no handle to close them with.
        plt.close(fig)
        return None

    output_dir = figure_dir(folder_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Keep zoomed figures from overwriting full-range ones.
    suffix = "" if tuple(xlim) == X_LIMITS else f"_{int(min(xlim))}-{int(max(xlim))}"
    output_path = output_dir / f"{file_name}_{result.file_key}{suffix}.png"
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_measurement_fits(
    measurement: MeasurementFitResult,
    *,
    stacked: bool = False,
    file_keys: list[str] | None = None,
    xlim: XLim | Sequence[XLim] = DEFAULT_WINDOWS,
    save: bool = True,
    dpi: int = 300,
) -> list[Path]:
    """Plot every file in a measurement.

    ``file_keys`` entries may each be an exact file key (``"delta5.0007"``), a
    whole delta group (``"delta5"`` -- every index in it), or a glob
    (``"delta5.00*"``). ``None`` plots every file in the measurement.
    """
    written: list[Path] = []
    for result in measurement.select(file_keys):
        for window in as_windows(xlim):
            output_path = plot_file_fit(
                result,
                folder_name=measurement.folder_name,
                file_name=measurement.file_name,
                stacked=stacked,
                xlim=window,
                save=save,
                dpi=dpi,
            )
            if output_path is not None:
                written.append(output_path)
    LOGGER.info("Wrote %d individual-fit figures", len(written))
    return written


def plot_fits(
    folder_name: str,
    name: str | None = None,
    *,
    file_keys: list[str] | None = None,
    xlim: XLim | Sequence[XLim] = DEFAULT_WINDOWS,
    stacked: bool = False,
    baseline: str = "saved",
    save: bool = True,
    dpi: int = 300,
) -> list[Path]:
    """Plot the saved fits for one measurement. Fits nothing.

        plot_fits("nn1120-3_pd_ceo2_004", "20260304_145524_pd_ceo2_004-000")
        plot_fits("nn1120-3_pd_ceo2_004")   # every measurement in the folder

    Loads the measurement via :func:`~src.utils.ir_fitting.load_measurement`, so
    it does **not** depend on ``ir_fitting.extra_peaks_base`` and writes nothing
    to the peak-fit folder -- only figures. With no peaks seeded this shows the
    existing fit reconstructed from ``*_CarbonylPeakFitParams.csv``, which is
    useful on its own. To see newly fitted peaks, run
    :func:`~src.utils.ir_fitting.fit_file` and pass its result to
    :func:`plot_measurement_fits`.

    Args:
        folder_name: Dataset folder, e.g. ``"nn1120-3_pd_ceo2_004"``.
        name: Measurement base name, e.g.
            ``"20260822_193302_pd_ceo2_000-026"``. Pass ``None`` to loop every
            measurement in the folder; one failing measurement is logged and
            skipped rather than aborting the rest.
        file_keys: Which files to plot, as a list. Each entry is an exact file
            key (``["delta5.0007"]``), a whole delta group
            (``["delta5"]`` -- every index in it), or a glob
            (``["delta5.00*"]``); entries may be mixed and may overlap.
            ``None`` plots every file in the measurement.
        xlim: One ``(high, low)`` window, or several. Defaults to
            ``DEFAULT_WINDOWS`` -- a zoomed figure and a full-range figure per
            file. y is rescaled to each window; the zoomed file gets a
            ``_1750-1900`` filename suffix so the two never collide.
        stacked: Residual in its own panel rather than offset below the data.
        baseline: ``"saved"`` or ``"recompute"``.
        save: Write figures to disk.
        dpi: Figure resolution.

    Returns:
        Paths of the figures written.
    """
    from src.utils.ir_fitting import load_measurement, measurement_names, subifg_dir

    if name is None:
        names = measurement_names(folder_name)
        LOGGER.info("%s: %d measurements", folder_name, len(names))
    else:
        names = [name]

    written: list[Path] = []
    for index, base_name in enumerate(names, start=1):
        if len(names) > 1:
            LOGGER.info("[%d/%d] %s", index, len(names), base_name)
        try:
            measurement = load_measurement(
                subifg_dir(folder_name) / base_name, baseline=baseline
            )
        except Exception as exc:  # one bad measurement must not abort the folder
            LOGGER.error("%s: %s", base_name, exc)
            continue
        written.extend(
            plot_measurement_fits(
                measurement,
                file_keys=file_keys,
                xlim=xlim,
                stacked=stacked,
                save=save,
                dpi=dpi,
            )
        )
    return written


if __name__ == "__main__":
    # Edit these constants to run a batch.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")

    folder_name = "nn1120-3_pd_ceo2_004"
    name = "20260304_145524_pd_ceo2_004-000"

    # No fitting, no dependency on ir_fitting.extra_peaks_base.
    # Emits a zoomed and a full-range figure per file; pass
    # xlim=ZOOM_LIMITS or xlim=X_LIMITS for just one.
    # Pass name=None to loop every measurement in the folder.
    paths = plot_fits(folder_name, name, file_keys=["delta10.*"])
    for item in paths:
        print(item)
