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
from src.visualizations._axes import (
    XLim,
    apply_reference_grid,
    as_windows,
    rescale_y_to_window,
)

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
        apply_reference_grid(axes, xlim)

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


def _group_gated(
    gated: Sequence[tuple[float, float, float]],
) -> list[tuple[list[float], float, float]]:
    """Group gated anchors by the extremum that gated them.

    One band gates every anchor within ``ANCHOR_GUARD_CM1`` of it, so a dense
    anchor set produces a dozen rejections that are all the *same* rejection.
    Rendering them one-per-anchor drew ten dotted lines 1 cm-1 apart -- which
    reads as a hatched block, not as anchors -- and wrote ten near-identical
    legend entries, one of which is the duplicated 2006 of spec.md 14.21.

    Grouping keeps every anchor (the duplicate included, because it carries
    double weight and hiding it would misreport the correction) while saying
    the thing once.

    Returns:
        ``[(anchors, where, fraction), ...]`` in first-appearance order.
        ``where`` is ``inf`` for the "outside window" rejections, which group
        together for the same reason.
    """
    groups: dict[tuple[float, float], list[float]] = {}
    order: list[tuple[float, float]] = []
    for anchor, where, fraction in gated:
        key = (round(float(where), 1), round(float(fraction), 3))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(float(anchor))
    return [(groups[key], key[0], key[1]) for key in order]


def _gated_label(anchors: Sequence[float], where: float, fraction: float) -> str:
    """One legend entry for one group of gated anchors."""
    if len(anchors) == 1:
        span = f"{anchors[0]:.0f}"
    else:
        # High-low, matching the descending x axis, plus the count -- which is
        # the only place the duplicated 2006 is still visible once grouped.
        span = f"{max(anchors):.0f}-{min(anchors):.0f} ({len(anchors)} anchors)"
    if not np.isfinite(where):
        return f"GATED {span} (outside window)"
    return f"GATED {span}<-{where:.0f} p={fraction:.2f}"


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
    for anchors, where, fraction in _group_gated(trace.anchors_gated):
        parts.append(_gated_label(anchors, where, fraction))
    # The lower segment's own anchors, marked "lo@" because they are a second
    # correction on a second array, not more points on the same line (spec.md
    # 14.10). A legend that merged the two could not say which one lost a
    # gated point -- 1955 is in both sets.
    if trace.lower_anchors_applied:
        parts.append("lo@" + "/".join(f"{a:.0f}" for a in trace.lower_anchors_applied))
    for anchors, where, fraction in _group_gated(trace.lower_anchors_gated):
        label = _gated_label(anchors, where, fraction)
        parts.append("LOW " + label.replace("(outside window)", "(outside segment)"))
    return ", ".join(parts)


def _draw_gated(
    axes,
    anchors: Sequence[float],
    where: float,
    color: str,
    drawn: set,
    tag: str,
) -> None:
    """Mark one group of gated anchors and the extremum responsible.

    A single anchor keeps the dotted line it always had. A run gets one shaded
    band instead of one line per anchor -- at 1 cm-1 spacing the lines merged
    into a block that looked like plot furniture rather than a guard verdict.

    ``drawn`` keys on the group so variants sharing a rejection do not stack
    markers, and the red ``where`` line keys on its own wavenumber so one band
    gating both anchor sets draws it once.
    """
    low, high = min(anchors), max(anchors)
    if (low, high, tag) not in drawn:
        drawn.add((low, high, tag))
        if low == high:
            axes.axvline(low, color=color, linestyle=":", linewidth=1.0)
        else:
            axes.axvspan(low, high, color=color, alpha=0.15, linewidth=0)
    if np.isfinite(where) and (where, "where") not in drawn:
        drawn.add((where, "where"))
        axes.axvline(where, color="tab:red", linestyle=":", linewidth=1.0)


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
        2, 1, figsize=(9, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1]}
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
            or trace.lower_anchors_applied
            or trace.lower_anchors_gated
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
    drawn: set[tuple[float, object]] = set()
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
        # One marker per REJECTION, not per anchor: a run of gated anchors is
        # shaded as a band and the extremum that gated them gets a single red
        # line, however many anchors it took out.
        for anchors, where, _ in _group_gated(trace.anchors_gated):
            _draw_gated(ax_raw, anchors, where, "0.5", drawn, "upper")
        # Lower-segment anchors: squares, not circles. They sit on a different
        # curve fitted by a different line, and at 1955 the two sets share a
        # wavenumber -- two markers at one x is the point, so they key on a
        # separate tag rather than colliding in `drawn`.
        for anchor in trace.lower_anchors_applied:
            if (anchor, "lower") in drawn:
                continue
            drawn.add((anchor, "lower"))
            value = float(
                np.interp(anchor, trace.wavenumbers[::-1], trace.baseline[::-1])
            )
            ax_raw.plot(
                anchor, value, "s", color="tab:green", markersize=5,
                markerfacecolor="tab:green", zorder=10,
            )
        for anchors, where, _ in _group_gated(trace.lower_anchors_gated):
            _draw_gated(ax_raw, anchors, where, "tab:green", drawn, "lower")

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

    ax_sub.axhline(0, color="0.7", linewidth=0.5)
    ax_sub.set_ylabel("baseline-subtracted")
    ax_sub.set_xlabel("Wavenumber (cm-1)")
    ax_sub.set_xlim(xlim)

    # Percentages in the legend are relative to the first variant, over the
    # region the two share -- see BaselineTrace.compared_over.
    for axes in (ax_raw, ax_sub):
        rescale_y_to_window(axes, reference.wavenumbers, xlim)
        apply_reference_grid(axes, xlim)

    # One legend, under the figure, rather than one box per panel inside it.
    # The anchor/split/seam annotations make these labels long enough that an
    # in-axes box covered the top of both panels -- which is where the flat
    # 2235-2250 check lives, and the whole point of the grid is reading values
    # off the plot. Handles come from ax_raw because it carries the raw trace
    # as well as every variant; ax_sub's labels are the same set.
    handles, labels = ax_raw.get_legend_handles_labels()
    # One text line per entry, as a fraction of figure height, plus a margin.
    # Reserved first so tight_layout does not lay the axes over the legend.
    reserved = min(0.3, 0.021 * len(labels) + 0.01)
    fig.legend(
        handles,
        labels,
        fontsize=7,
        loc="lower left",
        bbox_to_anchor=(0.01, 0.005),
        frameon=False,
    )
    fig.tight_layout(rect=(0, reserved, 1, 1))

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
