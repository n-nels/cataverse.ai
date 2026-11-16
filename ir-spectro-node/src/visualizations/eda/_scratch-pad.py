"""Scratch pad: kinetics data beside the time-series IR spectrum, per measurement.

Standalone, no CLI -- edit the constants in ``__main__``. Like
``plot_kinetics_fit.py`` but data only: no fits, segments or labels.

Left, stacked on a shared time axis: the pooled ``monomer_sum`` and
``cluster_sum`` points from ``<data.peak_fit>/<folder>/*_CarbonylPeakArea.csv``
(or under ``_reprocess/``, per the yaml ``data.plot_source``).

Right: every ``every_n``-th scan's lgRefl spectrum
(``utility.subtract_ifg.lg_refl_output``), raw -- no baseline -- and only
shifted so its mean within
``ANCHOR_HALF_WIDTH_CM1`` of ``SHIFT_ANCHOR_CM1`` is 0, coloured by time on a
colour bar. Scan times come from ``<read_params_output>/<measurement>.txt``,
with t = 0 at scan 0 (the same origin as the area CSVs). The spectra are read
over ``ROI_CM1`` and drawn over ``PLOT_CM1``. ``end_h`` truncates the spectra
(not the density panels) at that time; the colour bar runs linearly from 0 to
``end_h`` (or the run end). (A colour bar weighted toward the start was tried and
dropped as confusing, 2026-10-11.) Every 3rd-4th scan reads best on
a ~180-scan run (2026-10-11; linear and log time spacings were tried and
dropped).

Baselines were tried and dropped (2026-10-11): the live ``voigt_fit`` recipe,
a two-point line, ``arpls`` and ``asls`` over lam 1e3-1e7. Shifted at 2200,
the troughs near 2090 and 1960 cm-1 stay within about +-0.002 of 0 over the
whole run, and the 1750-1935 cm-1 shelf grows with the clusters, so it looks
like signal; any curved baseline removes part of it.

Behind the spectra, the monomer and cluster regions are shaded in their
density-panel colours. Each region runs from its outer ``ir_fitting.fit`` group
peaks (isotope-shifted) to midway to the next fitted peak (``group_bands``).

Presentation styling (``STYLE``, slide-sized ``FIGSIZE``): large Arial, open
top/right spines. Colours ("lagoon", 2026-10-11): time runs on ``CMAP``, deep
navy - cobalt - turquoise - apricot - vermilion, which changes hue and
lightness, so dynamic runs stay traceable. The groups are violet (monomer) and
dusty rose (cluster): their light region tints sit apart in hue from every
spectrum, and a thin line marks each region edge. Neutral (charcoal / grey)
groups were dropped: grey shading swallowed the dark spectra.

Output: ``<data.figures>/<folder>/scratch_kinetics_spectra/
<measurement>_kinetics_spectra.png``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.transforms import blended_transform_factory

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting import config as ir_config
from src.utils.kinetics.classification import sorted_trajectory
from src.utils.kinetics.writer import AREA_SUFFIX
from src.visualizations._source import source_dir

OUTPUT_SUBFOLDER = "scratch_kinetics_spectra"
OUTPUT_TAG = "_kinetics_spectra"
HOUR_S = 3600.0
ROI_CM1 = (1750.0, 2250.0)  # same window as analysis.io.import_data
SHIFT_ANCHOR_CM1 = 2200.0  # every spectrum is shifted to 0 here
ANCHOR_HALF_WIDTH_CM1 = 5.0
PLOT_CM1 = (1800.0, 2200.0)  # drawn window; y autoscales to it
SPECTRUM_LW = 1.0
EVERY_N = 4  # default: draw every n-th scan (scan 0 always included)
# Time: deep navy (t = 0) - cobalt - turquoise - apricot - vermilion (end).
CMAP = LinearSegmentedColormap.from_list(
    "lagoon", ["#0b2545", "#1f6fb2", "#1fb5a3", "#f4a259", "#e4572e"]
)
INK = "#2b2d42"  # axes, ticks and text
# (area peak, density-panel label, peak group, colour); the colour also
# shades that group's region on the spectra.
SUMS = (
    ("monomer_sum", "Monomer density (a.u.)", "monomer", "#6a4c93"),  # violet
    ("cluster_sum", "Carbonyl density (a.u.)", "cluster", "#b5838d"),  # dusty rose
)
BAND_ALPHA = 0.15
BAND_EDGE_LW = 1.0  # line at each region edge, in the region's colour
FIGSIZE = (12, 5.6)  # inches; fills a 16:9 slide below a title
DPI = 300
MARKER_SIZE = 6
STYLE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 15,
    "axes.labelsize": 16,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "axes.linewidth": 1.2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "xtick.major.width": 1.2,
    "ytick.major.width": 1.2,
    "xtick.major.size": 5,
    "ytick.major.size": 5,
}


def scan_times(folder_name: str, measurement: str) -> pd.DataFrame:
    """``scan`` index and ``time_s`` since scan 0, from the exp params log."""
    log_path = config.get_path(
        "utility.subtract_ifg.read_params_output", folder_name, f"{measurement}.txt"
    )
    log = pd.read_csv(
        log_path, header=None, names=["file_directory", "Date", "Time", "PKA", "NSS"]
    )
    files = log["file_directory"].str.split().str[0].str.strip("\"'")
    stamp = pd.to_datetime(
        log["Date"].str.strip() + " " + log["Time"].str.strip(), format="mixed"
    )
    table = pd.DataFrame(
        {
            "scan": files.str.rsplit(".", n=1).str[-1].astype(int),
            "time_s": (stamp - stamp.iloc[0]).dt.total_seconds(),
        }
    )
    return table.sort_values("scan").reset_index(drop=True)


def read_lgrefl(folder_name: str, measurement: str, scan: int) -> np.ndarray:
    """``(wavenumber, lgRefl)`` of one scan inside ``ROI_CM1``."""
    spectrum = pd.read_csv(
        config.get_path(
            "utility.subtract_ifg.lg_refl_output",
            folder_name,
            f"{measurement}.{scan:04d}",
        ),
        header=None,
    ).to_numpy(dtype=float)
    mask = (spectrum[:, 0] >= ROI_CM1[0]) & (spectrum[:, 0] <= ROI_CM1[1])
    return spectrum[mask]


def shifted(spectrum: np.ndarray) -> np.ndarray:
    """lgRefl minus its mean within ``ANCHOR_HALF_WIDTH_CM1`` of the anchor."""
    x, y = spectrum[:, 0], spectrum[:, 1]
    return y - y[np.abs(x - SHIFT_ANCHOR_CM1) <= ANCHOR_HALF_WIDTH_CM1].mean()


def group_bands() -> dict[str, tuple[float, float]]:
    """``(low, high)`` cm-1 of each ``SUMS`` group, from the fitted peak list.

    A region runs from its outer peaks to midway to the next fitted peak (or
    half the inner spacing, at the end of the list).
    """
    peaks = sorted(ir_config.get_peaks())
    bands = {}
    for _, _, group, _ in SUMS:
        members = ir_config.get_group_peaks(group)
        lo, hi = peaks.index(min(members)), peaks.index(max(members))
        low = (
            (peaks[lo - 1] + peaks[lo]) / 2
            if lo > 0
            else peaks[lo] - (peaks[lo + 1] - peaks[lo]) / 2
        )
        high = (
            (peaks[hi] + peaks[hi + 1]) / 2
            if hi < len(peaks) - 1
            else peaks[hi] + (peaks[hi] - peaks[hi - 1]) / 2
        )
        bands[group] = (low, high)
    return bands


def draw_bands(ax) -> None:
    """Shade each ``SUMS`` group's region and name it above the frame."""
    top = blended_transform_factory(ax.transData, ax.transAxes)
    for group, (low, high) in group_bands().items():
        color = next(c for _, _, g, c in SUMS if g == group)
        ax.axvspan(low, high, color=color, alpha=BAND_ALPHA, lw=0, zorder=0)
        for edge in (low, high):
            if PLOT_CM1[0] < edge < PLOT_CM1[1]:
                ax.axvline(edge, color=color, lw=BAND_EDGE_LW, alpha=0.6, zorder=0.5)
        mid = (max(low, PLOT_CM1[0]) + min(high, PLOT_CM1[1])) / 2
        ax.text(
            mid,
            1.01,
            group.capitalize(),
            transform=top,
            color=color,
            fontweight="bold",
            ha="center",
            va="bottom",
        )


def draw_spectra(
    ax,
    folder_name: str,
    measurement: str,
    times: pd.DataFrame,
    every_n: int,
    end_h: float | None = None,
) -> Normalize:
    """Every ``every_n``-th scan up to ``end_h``, shifted, over ``PLOT_CM1``.

    ``end_h`` None draws the whole run. Returns the time norm, linear from 0 to
    ``end_h`` (or the end of the run, if shorter).
    """
    run_h = times["time_s"].iloc[-1] / HOUR_S
    if end_h is not None:
        times = times[times["time_s"] <= end_h * HOUR_S]
    drawn = times.iloc[::every_n]
    norm = Normalize(0, run_h if end_h is None else min(end_h, run_h))
    cmap = plt.get_cmap(CMAP)
    for scan, time_s in zip(drawn["scan"], drawn["time_s"]):
        spectrum = read_lgrefl(folder_name, measurement, int(scan))
        y = shifted(spectrum)
        keep = (spectrum[:, 0] >= PLOT_CM1[0]) & (spectrum[:, 0] <= PLOT_CM1[1])
        ax.plot(
            spectrum[keep, 0],
            y[keep],
            color=cmap(norm(time_s / HOUR_S)),
            lw=SPECTRUM_LW,
        )
    draw_bands(ax)
    ax.set_xlim(PLOT_CM1[1], PLOT_CM1[0])  # wavenumber decreasing, IR convention
    ax.set_xlabel("Wavenumber (cm$^{-1}$)")
    ax.set_ylabel("log(1/R)")
    return norm


def plot_measurement(
    folder_name: str,
    area_path: Path,
    out_dir: Path,
    every_n: int = EVERY_N,
    end_h: float | None = None,
) -> Path:
    measurement = area_path.name.removesuffix(str(AREA_SUFFIX))
    areas = pd.read_csv(area_path)
    times = scan_times(folder_name, measurement)

    with plt.rc_context(STYLE):
        return _plot_measurement(
            measurement, areas, times, folder_name, out_dir, every_n, end_h
        )


def _plot_measurement(
    measurement: str,
    areas: pd.DataFrame,
    times: pd.DataFrame,
    folder_name: str,
    out_dir: Path,
    every_n: int,
    end_h: float | None,
) -> Path:
    fig = plt.figure(figsize=FIGSIZE, layout="constrained")
    grid = fig.add_gridspec(len(SUMS), 2, width_ratios=(1, 1.25))
    left = [fig.add_subplot(grid[0, 0])]
    left += [fig.add_subplot(grid[i, 0], sharex=left[0]) for i in range(1, len(SUMS))]
    for ax, (peak_name, ylabel, _, color) in zip(left, SUMS):
        time_s, values = sorted_trajectory(areas, peak_name)
        ax.plot(
            time_s / HOUR_S,
            values,
            "o",
            color=color,
            ms=MARKER_SIZE,
            alpha=0.75,
            mec="white",
            mew=0.6,
        )
        ax.set_ylim(bottom=0)
        ax.set_ylabel(ylabel)
        ax.margins(x=0)
    left[0].set_xlim(left=0)  # first area row is after t = 0; keep the 0 tick
    for ax in left[:-1]:
        ax.tick_params(labelbottom=False)
    left[-1].set_xlabel("Time (h)")

    ax_spec = fig.add_subplot(grid[:, 1])
    norm = draw_spectra(ax_spec, folder_name, measurement, times, every_n, end_h)
    colorbar = fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=plt.get_cmap(CMAP)),
        ax=ax_spec,
        pad=0.02,
        aspect=40,
    )
    colorbar.set_label("Time (h)")
    colorbar.outline.set_visible(False)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{measurement}{OUTPUT_TAG}.png"
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return output_path


def run_folder(
    folder_name: str,
    measurements: tuple[str, ...] = (),
    every_n: int = EVERY_N,
    end_h: float | None = None,
) -> list[Path]:
    """One figure per area CSV (or only ``measurements``, if given)."""
    source = source_dir(folder_name)
    area_files = sorted(source.glob(f"*{AREA_SUFFIX}"))
    if measurements:
        area_files = [
            p
            for p in area_files
            if p.name.removesuffix(str(AREA_SUFFIX)) in measurements
        ]
    if not area_files:
        raise FileNotFoundError(f"no *{AREA_SUFFIX} in {source}")
    out_dir = Path(config.get_path("data.figures", folder_name, OUTPUT_SUBFOLDER))
    written: list[Path] = []
    for area_path in area_files:
        try:
            written.append(
                plot_measurement(folder_name, area_path, out_dir, every_n, end_h)
            )
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"{area_path.name}: {exc}")
    return written


if __name__ == "__main__":
    FOLDER_NAME = "nn1120-3_pd_ceo2_003"
    MEASUREMENTS: tuple[str, ...] = (
        # "20260822_193302_pd_ceo2_000-026",
        # "20250105_130048_pd_ceo2_000-014",
        "20260214_170244_pd_ceo2_003-116",
    )  # e.g. ("20260630_141811_pd_ceo2_000-000",)
    EVERY_N = 3  # draw every n-th scan; 1 draws them all
    END_H = None  # draw spectra up to this time (h); None for the whole run

    for out in run_folder(FOLDER_NAME, MEASUREMENTS, EVERY_N, END_H):
        print(f"Wrote {out}")
