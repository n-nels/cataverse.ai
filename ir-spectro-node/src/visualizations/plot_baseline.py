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
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[2]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting.baseline import union_window
from src.utils.ir_fitting.result_types import (
    FileBaselineComparison,
    FileFitResult,
    MeasurementFitResult,
)
from src.visualizations._axes import XLim, as_windows, rescale_y_to_window

LOGGER = logging.getLogger(__name__)

X_LIMITS = (2250, 1750)
ZOOM_LIMITS = (1900, 1750)
"""Low-wavenumber window where the two candidate bands live."""

DEFAULT_WINDOWS = (ZOOM_LIMITS, X_LIMITS)
"""Emit a zoomed and a full-range figure per file unless told otherwise."""


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


def _anchor_label(trace) -> str:
    """Legend fragment describing what the split and anchor guards did."""
    parts = []
    if trace.split_applied is not None:
        parts.append(f"split {trace.split_applied:.0f} (seam {trace.seam_jump:+.1e})")
    if trace.split_gated is not None:
        split, where, fraction = trace.split_gated
        parts.append(f"SPLIT GATED {split:.0f}<-{where:.0f} p={fraction:.2f}")
    if trace.anchors_applied:
        parts.append("@" + "/".join(f"{a:.0f}" for a in trace.anchors_applied))
    for anchor, where, fraction in trace.anchors_gated:
        if np.isfinite(where):
            parts.append(f"GATED {anchor:.0f}<-{where:.0f} p={fraction:.2f}")
        else:
            parts.append(f"GATED {anchor:.0f} (outside window)")
    return ", ".join(parts)


def plot_baseline_comparison(
    comparison: FileBaselineComparison,
    *,
    folder_name: str,
    run_name: str,
    xlim: tuple[float, float] | None = None,
    save: bool = True,
    dpi: int = 300,
) -> Path | None:
    """Draw every baseline variant for one subIFG file on one figure.

    A pure renderer: it computes nothing. ``src/utils/ir_fitting/api.py``
    ::``compare_baselines`` builds the :class:`FileBaselineComparison` and calls
    this.

    Unlike :func:`plot_file_baseline`, which compares a recomputed baseline
    against the *stored* CSV column, this draws variant against variant -- the
    comparison an experiment needs.

    There is deliberately **no quality score**. The low-wavenumber bands are
    negative-going (``spec.md`` section 1), so these spectra carry features of
    both signs and the baseline is a centre-line estimator, not a lower
    envelope. An envelope-violation metric ranks the one file judged *good*
    worst of all eight judged files, so such a score is actively misleading.
    Judgement stays with the eye; this makes the comparison cheap to make.

    Args:
        comparison: One file's variants.
        folder_name: Dataset folder, used to resolve the output path.
        run_name: Experiment subfolder name.
        xlim: Display window, high to low. Defaults to the union of every
            variant's window, so a narrower variant's trace visibly *stops*
            rather than being cropped out of view.
        save: Write the figure to disk.
        dpi: Figure resolution.

    Returns:
        The written path, or None when ``save`` is False.
    """
    from src.utils.ir_fitting.api import baseline_experiment_dir

    traces = comparison.traces
    if not traces:
        return None

    if xlim is None:
        xlim = union_window(traces)

    fig, (ax_raw, ax_sub) = plt.subplots(
        2, 1, figsize=(8, 6.5), sharex=True, gridspec_kw={"height_ratios": [1, 1]}
    )

    reference = traces[0]
    ax_raw.plot(
        reference.wavenumbers,
        reference.raw,
        color="black",
        linewidth=1.2,
        label="raw subIFG",
        zorder=5,
    )

    colors = plt.get_cmap("tab10").colors
    for index, trace in enumerate(traces):
        color = colors[index % len(colors)]
        style = "-" if index == 0 else "--"

        label = trace.label
        if not trace.is_reference:
            label += f"  ({trace.moved_pct_of_range:.1f}%)"
        if trace.window != reference.window:
            label += f"  [{trace.window[0]:.0f}-{trace.window[1]:.0f}]"
        if trace.degenerate:
            label += "  DEGENERATE"
        if (
            trace.anchors_applied
            or trace.anchors_gated
            or trace.split_applied is not None
            or trace.split_gated is not None
        ):
            label += f"  [{_anchor_label(trace)}]"

        ax_raw.plot(
            trace.wavenumbers,
            trace.baseline,
            color=color,
            linewidth=1.1,
            linestyle=style,
            label=label,
        )
        ax_sub.plot(
            trace.wavenumbers,
            trace.corrected,
            color=color,
            linewidth=1.1,
            linestyle=style,
            label=label,
        )

    # Anchor markers: filled where the baseline was pinned, hollow with an x
    # where the guard rejected the anchor. Drawn once per distinct wavenumber,
    # since variants sharing an anchor would otherwise stack markers.
    drawn: set[tuple[float, bool]] = set()
    for trace in traces:
        for anchor in trace.anchors_applied:
            if (anchor, True) in drawn:
                continue
            drawn.add((anchor, True))
            value = float(
                np.interp(
                    anchor,
                    trace.wavenumbers[::-1],
                    trace.baseline[::-1],
                )
            )
            ax_raw.plot(
                anchor, value, "o", color="black", markersize=5,
                markerfacecolor="black", zorder=10,
            )
        for anchor, where, _ in trace.anchors_gated:
            if (anchor, False) in drawn:
                continue
            drawn.add((anchor, False))
            ax_raw.axvline(anchor, color="0.5", linestyle=":", linewidth=1.0)
            if np.isfinite(where):
                ax_raw.axvline(where, color="tab:red", linestyle=":", linewidth=1.0)

    # The seam of a split baseline, on both panels: the interface is where a
    # two-segment baseline is most likely to be wrong (spec.md section 14.4),
    # and it is judged by eye like everything else here.
    for split in sorted(
        {trace.split_applied for trace in traces if trace.split_applied is not None}
    ):
        for axis in (ax_raw, ax_sub):
            axis.axvline(
                split, color="tab:purple", linestyle="-.", linewidth=1.0, alpha=0.7
            )

    ax_raw.set_ylabel("Log Reflectance")
    title = comparison.subifg_path.name
    if comparison.verdict:
        title += f"   [{comparison.verdict}]"
    ax_raw.set_title(title, fontsize=9)
    ax_raw.legend(fontsize=7, loc="upper right", ncol=2)

    ax_sub.axhline(0, color="0.7", linewidth=0.5)
    ax_sub.set_ylabel("baseline-subtracted")
    ax_sub.set_xlabel("Wavenumber (cm-1)")
    ax_sub.set_xlim(xlim)
    ax_sub.legend(fontsize=7, loc="upper right", ncol=2)

    # Percentages in the legend are relative to the first variant, over the
    # region the two share -- see BaselineTrace.compared_over.
    for axes in (ax_raw, ax_sub):
        rescale_y_to_window(axes, reference.wavenumbers, xlim)

    fig.tight_layout()

    if not save:
        plt.close(fig)
        return None

    output_dir = baseline_experiment_dir(folder_name, run_name)
    output_path = output_dir / f"{comparison.subifg_path.name}.png"
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_measurement_baselines(
    measurement: MeasurementFitResult,
    *,
    file_keys: list[str] | None = None,
    compare_saved: bool = True,
    xlim: XLim | Sequence[XLim] = DEFAULT_WINDOWS,
    save: bool = True,
    dpi: int = 300,
) -> list[Path]:
    """Plot baselines for every file in a measurement.

    ``file_keys`` entries may each be an exact file key (``"delta5.0007"``), a
    whole delta group (``"delta5"`` -- every index in it), or a glob
    (``"delta5.00*"``). ``None`` plots every file in the measurement.
    """
    written: list[Path] = []
    for result in measurement.select(file_keys):
        for window in as_windows(xlim):
            output_path = plot_file_baseline(
                result,
                folder_name=measurement.folder_name,
                file_name=measurement.file_name,
                compare_saved=compare_saved,
                xlim=window,
                save=save,
                dpi=dpi,
            )
            if output_path is not None:
                written.append(output_path)
    LOGGER.info("Wrote %d baseline figures", len(written))
    return written


def plot_baselines(
    folder_name: str,
    name: str | None = None,
    *,
    file_keys: list[str] | None = None,
    xlim: XLim | Sequence[XLim] = DEFAULT_WINDOWS,
    baseline: str = "saved",
    compare_saved: bool = True,
    save: bool = True,
    dpi: int = 300,
) -> list[Path]:
    """Plot the saved baselines for one measurement. Fits nothing.

    The entry point for looking at baselines:

        plot_baselines("nn1120-4_pd_ceo2_000", "20260822_193302_pd_ceo2_000-026")
        plot_baselines("nn1120-4_pd_ceo2_000")   # every measurement in the folder

    Loads the measurement via :func:`~src.utils.ir_fitting.load_measurement`, so
    it does **not** depend on ``ir_fitting.extra_peaks_base`` and writes nothing
    to the peak-fit folder -- only figures. By default emits two figures per
    file: the low-wavenumber window where the candidate bands live, and the full
    ROI. Pass ``xlim=ZOOM_LIMITS`` or ``xlim=X_LIMITS`` for just one.

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
        baseline: ``"saved"`` or ``"recompute"``.
        compare_saved: Overlay the saved baseline when recomputing.
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
            plot_measurement_baselines(
                measurement,
                file_keys=file_keys,
                compare_saved=compare_saved,
                xlim=xlim,
                save=save,
                dpi=dpi,
            )
        )
    return written


if __name__ == "__main__":
    # Edit these constants to run a batch.
    #
    # This module *views* baselines. To experiment with baseline settings or
    # window size, use src/utils/ir_fitting/api.py::compare_baselines -- the
    # experiment is orchestrated there and only rendered here.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")

    folder_name = "nn1120-4_pd_ceo2_000"
    name = "20260715_094622_pd_ceo2_000-007"

    # No fitting, no dependency on ir_fitting.extra_peaks_base.
    # Drop file_keys to plot every file; name=None loops every measurement.
    # xlim=DEFAULT_WINDOWS emits a zoomed and a full-range figure per file.
    for item in plot_baselines(folder_name, name, xlim=X_LIMITS, file_keys=["delta10"]):
        print(item)
