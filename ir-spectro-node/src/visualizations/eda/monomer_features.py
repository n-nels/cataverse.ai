"""Draw each measurement's kinetic segments and fits (``fit_cli --mode segments``).

EDA fork of ``src/visualizations/monomer_features.py`` with less on the plot:
no smoothed (boundaries) curve, no monomer/cluster max markers, no growth
onset/latch lines, no cluster plateau line, no Peak_1988 axis and no title. Figures are written next to the original's,
as ``*_kinetic_segments_eda.png`` (catalog ``kinetic_segments_eda.csv``).

Standalone, no CLI -- edit ``FOLDER_NAME`` in ``__main__``. Design of the
segments: src/utils/kinetics/spec-working.md. (The earlier LaMer I/II/III
domain catalog of the monomer-kinetics loop, docs/JOURNAL_monomer-kinetics.md,
was replaced by these segments; it is in git history.)

Inputs, per measurement:

- ``<data.peak_fit>/<folder>/_reprocess/*_CarbonylPeakArea.csv``: the data;
- ``<...>/_reprocess/<FIT_SUBFOLDER>/*_CarbonylKineticFeatures.csv``: the
  classification, growth onset, latch, monomer max and spike. Required: run
  ``scripts\\run_kinetics_fit.py --folder <folder>`` (``--classify-only`` is
  enough for the segments without fits);
- ``*_CarbonylKineticParams.csv`` next to it: the segment fits, drawn when
  present.

One figure per measurement, two panels on a shared time axis:

- top, monomer_sum;
- bottom, cluster_sum.

Each panel shows the raw pooled points, the shaded segments
(``segments.plan_segments``) and each fitted segment's curve
(``segments.segment_curve``). Output: ``*_kinetic_segments_eda.png`` plus
``kinetic_segments_eda.csv`` (the features joined with the sums' segment fits,
one row per measurement) under ``<data.figures>/<folder>/plot_kinetic_segments/``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.kinetics.classification import sorted_trajectory
from src.utils.kinetics.segments import (
    FEATURES_SUFFIX,
    PARAMS_SUFFIX,
    plan_segments,
    segment_curve,
)
from src.utils.kinetics.writer import AREA_SUFFIX, SEARCH_ROOT

INPUT_SUBFOLDER = "_reprocess"
FIT_SUBFOLDER = "_test"
HOUR_S = 3600.0
MARKER_SIZE = 4.5  # data points, in points (the original module uses "." at 3)
OUTPUT_TAG = "_eda"  # keeps these figures apart from the original module's
FIGSIZE = (5, 5)  # inches; small, so default text reads large (cf. _scratch-pad.py)
DPI = 300
SEGMENT_FONTSIZE = 9
AXIS_FONTSIZE = 12  # axis labels and tick values (matplotlib default 10)
LABEL_ROWS = 3  # segment labels cycle over this many rows at the panel top
LABEL_ROW_STEP = 0.08  # axes fraction per label row

SEGMENT_COLORS = {
    "adsorption": "tab:green",
    "supersaturation": "tab:green",
    "depletion": "tab:blue",
    "ripening": "tab:grey",
    "pre_nucleation": "tab:green",
    "burst_nucleation": "darkgoldenrod",
    "diffusion_growth": "tab:red",
}
SPAN_ALPHA = 0.08
# The nucleation span is narrow (~2 h), so it gets a stronger fill to show up.
SEGMENT_ALPHAS = {"burst_nucleation": 0.3}
Y_LABELS = {
    "monomer_sum": "Monomer Density (a.u.)",
    "cluster_sum": "Carbonyl Density (a.u.)",
}
# Display names only; the params CSVs keep the segments.py names.
SEGMENT_LABELS = {
    "pre_nucleation": "pre-nucleation",
    "burst_nucleation": "nucleation",
    "diffusion_growth": "growth",
}


def input_dir(folder_name: str) -> Path:
    return SEARCH_ROOT / folder_name / INPUT_SUBFOLDER


def fit_dir(folder_name: str) -> Path:
    return input_dir(folder_name) / FIT_SUBFOLDER


def output_dir(folder_name: str) -> Path:
    return Path(
        config.get_path(
            "data.figures", folder_name, config.get_path("data.plot_kinetic_segments")
        )
    )


def _segment_bounds(segment: Any, time_s: np.ndarray) -> tuple[float, float]:
    """A planned segment's ``(start, end)`` in seconds, open ends resolved."""
    start = segment.t_start if segment.t_start is not None else float(time_s[0])
    end = segment.t_end if segment.t_end is not None else float(time_s[-1])
    return start, end


def _draw_panel(
    ax: Any,
    df: pd.DataFrame,
    sum_name: str,
    segments: list[Any],
    params: pd.DataFrame,
    color: str,
) -> None:
    """Data, shaded segments and fits of one sum."""
    time_s, values = sorted_trajectory(df, sum_name)
    if time_s.size == 0:
        ax.text(0.5, 0.5, f"no {sum_name} rows", transform=ax.transAxes, ha="center")
        return
    for i, segment in enumerate(segments):
        start, end = _segment_bounds(segment, time_s)
        seg_color = SEGMENT_COLORS.get(segment.name, "tab:grey")
        ax.axvspan(
            start / HOUR_S,
            end / HOUR_S,
            color=seg_color,
            alpha=SEGMENT_ALPHAS.get(segment.name, SPAN_ALPHA),
            lw=0,
        )
        ax.text(
            start / HOUR_S,
            0.98 - (i % LABEL_ROWS) * LABEL_ROW_STEP,
            " " + SEGMENT_LABELS.get(segment.name, segment.name),
            transform=ax.get_xaxis_transform(),
            ha="left",
            va="top",
            fontsize=SEGMENT_FONTSIZE,
            color=seg_color,
        )
    ax.plot(
        time_s / HOUR_S,
        values,
        "o",
        color=color,
        ms=MARKER_SIZE,
        alpha=0.5,
        mec="none",
        label=sum_name,
    )

    rows = params[params["Peak_Name"] == sum_name] if not params.empty else params
    for _, record in rows.iterrows():
        if record["model"] == "none":
            continue
        grid = np.linspace(record["t_start_s"], record["t_end_s"], 200)
        curve = segment_curve(record, grid)
        if not np.isfinite(curve).any():
            continue
        ax.plot(
            grid / HOUR_S,
            curve,
            "-",
            color=SEGMENT_COLORS.get(record["segment"], "k"),
            lw=2.2,
            label=(
                f"{SEGMENT_LABELS.get(record['segment'], record['segment'])}: "
                f"{record['model']}  R²={record['r^2']:.3f}"
            ),
        )
    # Headroom so the label rows sit above the data, with the axis from 0.
    label_band = min(len(segments), LABEL_ROWS) * LABEL_ROW_STEP + 0.04
    ax.set_ylim(0, ax.get_ylim()[1] / (1 - label_band))
    ax.set_ylabel(Y_LABELS.get(sum_name, f"{sum_name} (a.u.)"))


def _plot_file(
    measurement: str,
    df: pd.DataFrame,
    features: dict[str, Any],
    params: pd.DataFrame,
    out_dir: Path,
) -> Path:
    plan = plan_segments(features)
    fig, (ax_m, ax_c) = plt.subplots(2, 1, figsize=FIGSIZE, sharex=True)

    _draw_panel(ax_m, df, "monomer_sum", plan["monomer"], params, "tab:blue")
    _draw_panel(ax_c, df, "cluster_sum", plan["cluster"], params, "tab:orange")

    # for ax in (ax_m, ax_c):
    #     ax.legend(loc="upper right", fontsize=7.5)
    for ax in (ax_m, ax_c):
        ax.margins(x=0)  # time axis spans exactly the data
        ax.tick_params(labelsize=AXIS_FONTSIZE)
        ax.yaxis.label.set_size(AXIS_FONTSIZE)
    ax_c.set_xlabel("Time (h)", fontsize=AXIS_FONTSIZE)

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{measurement}_kinetic_segments{OUTPUT_TAG}.png"
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return output_path


def _catalog_row(features: dict[str, Any], params: pd.DataFrame) -> dict[str, Any]:
    """Features plus each sum segment's model, point count and R²."""
    row = dict(features)
    if params.empty:
        return row
    sums = params[params["Peak_Name"].isin(["monomer_sum", "cluster_sum"])]
    for _, record in sums.iterrows():
        prefix = f"{record['Peak_Name']}_{record['segment']}"
        row[f"{prefix}_model"] = record["model"]
        row[f"{prefix}_n_points"] = record["n_points"]
        row[f"{prefix}_r2"] = record["r^2"]
    return row


def process_file(area_path: Path, folder_name: str, out_dir: Path) -> dict[str, Any]:
    measurement = area_path.name.removesuffix(str(AREA_SUFFIX))
    features_path = fit_dir(folder_name) / f"{measurement}{FEATURES_SUFFIX}"
    if not features_path.exists():
        raise FileNotFoundError(
            f"{features_path.name} missing; run scripts\\run_kinetics_fit.py "
            f"--folder {folder_name} (--classify-only is enough) first"
        )
    features = pd.read_csv(features_path).iloc[0].to_dict()
    params_path = fit_dir(folder_name) / f"{measurement}{PARAMS_SUFFIX}"
    params = pd.read_csv(params_path) if params_path.exists() else pd.DataFrame()
    _plot_file(measurement, pd.read_csv(area_path), features, params, out_dir)
    return _catalog_row(features, params)


def run_folder(folder_name: str) -> pd.DataFrame:
    """Every area CSV of one dataset: figures + ``kinetic_segments_eda.csv``."""
    source = input_dir(folder_name)
    area_files = sorted(source.glob(f"*{AREA_SUFFIX}"))
    if not area_files:
        raise FileNotFoundError(f"no *{AREA_SUFFIX} in {source}")
    out_dir = output_dir(folder_name)

    rows: list[dict[str, Any]] = []
    for area_path in area_files:
        try:
            rows.append(process_file(area_path, folder_name, out_dir))
        except Exception as exc:  # noqa: BLE001 - record and keep going
            rows.append({"Measurement": area_path.name, "error": str(exc)})

    catalog = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(out_dir / f"kinetic_segments{OUTPUT_TAG}.csv", index=False)
    return catalog


if __name__ == "__main__":
    FOLDER_NAME = "nn1120-3_pd_ceo2_002"
    result = run_folder(FOLDER_NAME)
    print(f"Wrote {len(result)} figures to {output_dir(FOLDER_NAME)}")
    columns = [
        c
        for c in (
            "Measurement",
            "classification",
            "monomer_max_s",
            "spike_detected",
            "spike_prominence",
            "error",
        )
        if c in result.columns
    ]
    with pd.option_context("display.max_rows", None, "display.width", 240):
        print(result[columns])
