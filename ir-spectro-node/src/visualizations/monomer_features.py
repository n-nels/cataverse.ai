"""Draw each measurement's kinetic segments and fits (``fit_cli --mode segments``).

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
- bottom, cluster_sum, with the detector peak (``PEAK_NAME``, Peak_1988) on
  its own axis.

Each panel shows the raw pooled points, the centered running median that
sets the boundaries (``segments.smoothed``), the shaded segments
(``segments.plan_segments``) and each fitted segment's curve
(``segments.segment_curve``). The growth onset and latch are lines on both
panels. Output: ``*_kinetic_segments.png`` plus ``kinetic_segments.csv`` (the
features joined with the sums' segment fits, one row per measurement) under
``<data.figures>/<folder>/plot_kinetic_segments/``.
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

path = Path(__file__).resolve().parents[2]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.kinetics.classification import PEAK_NAME, sorted_trajectory
from src.utils.kinetics.segments import (
    FEATURES_SUFFIX,
    PARAMS_SUFFIX,
    plan_segments,
    segment_curve,
    smoothed,
)
from src.utils.kinetics.writer import AREA_SUFFIX, SEARCH_ROOT

INPUT_SUBFOLDER = "_reprocess"
FIT_SUBFOLDER = "_test"
HOUR_S = 3600.0

SEGMENT_COLORS = {
    "adsorption": "tab:green",
    "supersaturation": "tab:green",
    "depletion": "tab:blue",
    "ripening": "tab:grey",
    "pre_nucleation": "tab:green",
    "burst_nucleation": "tab:purple",
    "diffusion_growth": "tab:red",
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
    """Data, smoothed curve, shaded segments and fits of one sum."""
    time_s, values = sorted_trajectory(df, sum_name)
    if time_s.size == 0:
        ax.text(0.5, 0.5, f"no {sum_name} rows", transform=ax.transAxes, ha="center")
        return
    for i, segment in enumerate(segments):
        start, end = _segment_bounds(segment, time_s)
        seg_color = SEGMENT_COLORS.get(segment.name, "tab:grey")
        ax.axvspan(start / HOUR_S, end / HOUR_S, color=seg_color, alpha=0.08)
        ax.text(
            (start + end) / 2 / HOUR_S,
            0.99 if i % 2 == 0 else 0.92,
            segment.name,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
            color=seg_color,
        )
    ax.plot(time_s / HOUR_S, values, ".", color=color, ms=3, alpha=0.35, label=sum_name)
    ax.plot(
        time_s / HOUR_S,
        smoothed(values),
        "-",
        color=color,
        lw=0.8,
        alpha=0.7,
        label="smoothed (boundaries)",
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
            label=f"{record['segment']}: {record['model']}  R²={record['r^2']:.3f}",
        )
    ax.set_ylabel(f"{sum_name} (a.u.)", color=color)
    ax.tick_params(axis="y", labelcolor=color)


def _event_lines(ax: Any, features: dict[str, Any]) -> list[tuple[Any, str]]:
    """Growth onset and latch, as vertical lines."""
    drawn: list[tuple[Any, str]] = []
    for key, style, color, name in (
        ("growth_onset_s", "-.", "tab:brown", "growth onset"),
        ("latch_time_s", ":", "tab:red", "latch"),
    ):
        t = features.get(key, np.nan)
        if np.isfinite(t):
            line = ax.axvline(t / HOUR_S, color=color, ls=style, lw=1.5)
            drawn.append((line, f"{name} {t / HOUR_S:.1f} h"))
    return drawn


def _plot_file(
    measurement: str,
    df: pd.DataFrame,
    features: dict[str, Any],
    params: pd.DataFrame,
    out_dir: Path,
) -> Path:
    plan = plan_segments(features)
    fig, (ax_m, ax_c) = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)

    _draw_panel(ax_m, df, "monomer_sum", plan["monomer"], params, "tab:blue")
    t_m = features.get("monomer_max_s", np.nan)
    if np.isfinite(t_m):
        ax_m.plot(
            t_m / HOUR_S,
            features["monomer_max_au"],
            "*",
            color="tab:blue",
            ms=14,
            label=f"monomer max {t_m / HOUR_S:.1f} h",
        )

    _draw_panel(ax_c, df, "cluster_sum", plan["cluster"], params, "tab:orange")
    t_c = features.get("cluster_max_s", np.nan)
    if np.isfinite(t_c):
        ax_c.plot(
            t_c / HOUR_S,
            features["cluster_max_au"],
            "*",
            color="tab:orange",
            ms=14,
            label=f"cluster max {t_c / HOUR_S:.1f} h",
        )
    plateau = features.get("cluster_plateau_au", np.nan)
    time_c, _ = sorted_trajectory(df, "cluster_sum")
    if np.isfinite(plateau) and np.isfinite(t_c) and time_c.size:
        ax_c.hlines(
            plateau,
            t_c / HOUR_S,
            time_c[-1] / HOUR_S,
            color="tab:orange",
            ls="--",
            lw=1,
            label=f"plateau {plateau:.3f}",
        )

    # The detector peak sits ~an order of magnitude below cluster_sum.
    time_p, values_p = sorted_trajectory(df, PEAK_NAME)
    if time_p.size:
        ax_p = ax_c.twinx()
        ax_p.plot(
            time_p / HOUR_S, smoothed(values_p), "-", color="tab:brown", lw=1, alpha=0.6
        )
        ax_p.set_ylabel(f"{PEAK_NAME}, smoothed (a.u.)", color="tab:brown")
        ax_p.tick_params(axis="y", labelcolor="tab:brown")

    for ax in (ax_m, ax_c):
        handles, labels = ax.get_legend_handles_labels()
        for line, label in _event_lines(ax, features):
            handles.append(line)
            labels.append(label)
        ax.legend(handles, labels, loc="upper right", fontsize=7.5)
    ax_c.set_xlabel("Time (h)")

    label = features.get("classification")
    title = f"{measurement}   {label if isinstance(label, str) else 'unclassified'}"
    if label == "discontinuous":
        detected = features.get("spike_detected") in (True, 1)
        score = features.get("spike_prominence", np.nan)
        title += f"   spike: {'yes' if detected else 'no'}"
        if np.isfinite(score):
            title += f" (prominence {score:.1f}, rise {features.get('spike_rise', np.nan):.1f})"
    if params.empty:
        title += "   [no fits: params file missing]"
    ax_m.set_title(title, fontsize=10)

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{measurement}_kinetic_segments.png"
    fig.savefig(output_path, dpi=110)
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
    """Every area CSV of one dataset: figures + ``kinetic_segments.csv``."""
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
    catalog.to_csv(out_dir / "kinetic_segments.csv", index=False)
    return catalog


if __name__ == "__main__":
    FOLDER_NAME = "nn1120-4_pd_ceo2_000"
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
