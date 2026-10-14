"""Equilibrium carbonyl density ``q_e`` per measurement: monomer and cluster.

Standalone, no CLI -- edit the constants in ``__main__``. Promoted from
``eda/_scratch-pad.py`` (monomer only). Reads the segment fits written by
``scripts\\run_kinetics_fit.py --folder <folder>`` (default ``--mode segments``)
from ``<data.peak_fit>/<folder>/<INPUT_SUBFOLDER>/<FIT_SUBFOLDER>/
*_CarbonylKineticParams.csv``.

Per measurement and sum, ``q_e`` comes from the **first** segment (the
smallest ``t_start_s``), i.e. before the division at nucleation; nothing after
it is used (``segments.plan_segments``):

- monomer_sum: ``supersaturation`` if discontinuous, else ``adsorption``;
- cluster_sum: ``pre_nucleation`` if discontinuous, else ``adsorption``. A
  discontinuous file without a growth onset has only ``ripening``, which is
  past the division, so it gets no ``q_e`` (noted, drawn as a missing slot);
- the column follows that row's model: ``pfo_q_e_au`` for pfo,
  ``pfo-sec_q_e_au`` for secondary_pfo. Today monomer_sum is always
  secondary_pfo and cluster_sum pfo (spec-working.md §2).

Only successful reference samples are kept: in
``<data.exp_params>/<folder>/<measurement>_expParams.json``,
``filename_flags.is_reference`` is true and ``filename_flags.exp_success`` is
not false (a missing ``exp_success`` counts as success). A measurement without
that JSON, or a failed reference, is dropped and listed.

Two panels on a shared x axis: monomer (top), cluster (bottom). The x axis
("Time") is evenly spaced: one slot per kept params file in sorted (= time)
order, not proportional to time. Every slot gets a tick; at most
``MAX_DATE_LABELS`` are labelled with the measurement's mm-dd date. Missing
fits keep their slot (dotted line, per panel) and are listed; ``q_e == 0``
(pinned at the bound) is drawn hollow. Colour is the regime; there is no
legend or title. Output: ``<data.figures>/<folder>/carbonyl_density.tiff``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

path = Path(__file__).resolve().parents[2]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.kinetics.segments import PARAMS_SUFFIX
from src.utils.kinetics.writer import SEARCH_ROOT

EXP_PARAMS_SUFFIX = "_expParams.json"
# (column prefix, Peak_Name), top panel first.
SUMS = (("monomer", "monomer_sum"), ("cluster", "cluster_sum"))
YLABELS = ("Monomer Density (a.u.)", "Carbonyl Density (a.u.)")  # per panel
# Segments before the division at nucleation (segments.plan_segments).
PRE_DIVISION = {"adsorption", "supersaturation", "pre_nucleation"}
Q_E_COLUMN = {"pfo": "pfo_q_e_au", "secondary_pfo": "pfo-sec_q_e_au"}
FIGSIZE = (4, 5)  # inches: single journal column, two stacked panels
MAX_DATE_LABELS = 6  # x ticks sit on every measurement; at most this many dated
# regime -> (colour, marker, legend label). Blue/orange stay apart under colour
# blindness (green/red does not); the marker shape is a second, colour-free cue.
REGIME_STYLES = {
    "continuous": ("#2a78d6", "o", "Continuous"),
    "discontinuous": ("#eb6834", "D", "Discontinuous"),
    "unclassified": ("#8a8984", "s", "Unclassified"),
}
MARKER_SIZE = 4.5
INK = "#3d3d3a"  # axes, ticks and labels: dark grey, softer than black
GRID = "#e6e5e0"
STYLE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "axes.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": INK,
    "ytick.color": INK,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "xtick.minor.width": 0.5,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "xtick.minor.size": 1.5,
}


def first_segment_q_e(params: pd.DataFrame, sum_name: str) -> dict:
    """``q_e`` of the first segment of ``sum_name``; NaN past the division."""
    rows = params[params["Peak_Name"] == sum_name].sort_values("t_start_s")
    if rows.empty:
        return {"q_e_au": np.nan, "note": f"no {sum_name} rows"}
    record = rows.iloc[0]
    out = {
        "segment": record["segment"],
        "model": record["model"],
        "n_points": record["n_points"],
        "r^2": record["r^2"],
    }
    if record["segment"] not in PRE_DIVISION:
        return {**out, "q_e_au": np.nan, "note": "no pre-division segment"}
    column = Q_E_COLUMN.get(record["model"])
    q_e = float(record[column]) if column else np.nan
    return {**out, "q_e_au": q_e, "note": "" if np.isfinite(q_e) else "no fit"}


def measurement_q_e(params_path: Path) -> dict:
    """Monomer and cluster ``q_e`` of one params file, as one wide row."""
    measurement = params_path.name.removesuffix(str(PARAMS_SUFFIX))
    params = pd.read_csv(params_path)
    row = {
        "Measurement": measurement,
        "short": measurement.rsplit("_", 1)[-1],
        "date": f"{measurement[4:6]}-{measurement[6:8]}",  # YYYYMMDD_... -> mm-dd
        "regime": params["regime"].iloc[0] if not params.empty else np.nan,
    }
    for prefix, sum_name in SUMS:
        for key, value in first_segment_q_e(params, sum_name).items():
            row[f"{prefix}_{key}"] = value
    return row


def filename_flags(folder_name: str, measurement: str) -> dict | None:
    """``filename_flags`` from the expParams JSON; None if the JSON is missing."""
    json_path = Path(
        config.get_path(
            "data.exp_params", folder_name, f"{measurement}{EXP_PARAMS_SUFFIX}"
        )
    )
    if not json_path.exists():
        return None
    with json_path.open() as handle:
        return json.load(handle).get("filename_flags", {})


def collect(folder_name: str, input_subfolder: str, fit_subfolder: str) -> pd.DataFrame:
    """First-segment ``q_e`` of every successful reference of one dataset."""
    source = SEARCH_ROOT / folder_name / input_subfolder / fit_subfolder
    files = sorted(source.glob(f"*{PARAMS_SUFFIX}"))
    if not files:
        raise FileNotFoundError(f"no *{PARAMS_SUFFIX} in {source}")
    kept: list[Path] = []
    no_json: list[str] = []
    failed: list[str] = []
    for params_path in files:
        measurement = params_path.name.removesuffix(str(PARAMS_SUFFIX))
        flags = filename_flags(folder_name, measurement)
        if flags is None:
            no_json.append(measurement)
        elif not flags.get("is_reference", False):
            continue
        elif flags.get("exp_success", True) is False:
            failed.append(measurement)
        else:
            kept.append(params_path)
    print(f"{len(kept)}/{len(files)} measurements are successful references")
    if no_json:
        print(f"dropped, no {EXP_PARAMS_SUFFIX}: {', '.join(no_json)}")
    if failed:
        print(f"dropped, exp_success false: {', '.join(failed)}")
    if not kept:
        raise FileNotFoundError(f"no successful reference measurements in {source}")
    table = pd.DataFrame([measurement_q_e(p) for p in kept])
    table.index.name = "index"
    return table


def plot_panel(ax, table: pd.DataFrame, column: str) -> None:
    """One sum's ``q_e`` per measurement, coloured and shaped by regime."""
    for regime, (color, marker, _) in REGIME_STYLES.items():
        sub = table[table["regime"] == regime]
        if sub.empty:
            continue
        pinned = sub[column] == 0
        # A thin white ring keeps neighbouring markers apart where they touch.
        ax.plot(
            sub.index[~pinned],
            sub[column][~pinned],
            marker,
            ls="none",
            color=color,
            mec="white",
            mew=0.5,
            ms=MARKER_SIZE,
            zorder=3,
        )
        if pinned.any():
            ax.plot(
                sub.index[pinned],
                sub[column][pinned],
                marker,
                ls="none",
                mfc="white",
                mec=color,
                mew=1.0,
                ms=MARKER_SIZE,
                zorder=3,
            )
    for i in table[table[column].isna()].index:
        ax.axvline(i, color="#b4b2a9", lw=0.6, ls=":", zorder=1)
    ax.grid(axis="y", color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)


def legend_handles(table: pd.DataFrame) -> list[Line2D]:
    """Legend entries: continuous and discontinuous always, unclassified if present."""
    shown = {"continuous", "discontinuous"} | set(table["regime"].dropna())
    return [
        Line2D(
            [],
            [],
            marker=marker,
            ls="none",
            color=color,
            mec="white",
            mew=0.5,
            ms=MARKER_SIZE + 1,
            label=label,
        )
        for regime, (color, marker, label) in REGIME_STYLES.items()
        if regime in shown
    ]


def plot(table: pd.DataFrame, output_path: Path) -> Path:
    """Monomer over cluster ``q_e``, evenly spaced, every ``step``-th date labelled."""
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(len(SUMS), 1, figsize=FIGSIZE, sharex=True)
        for ax, (prefix, _), ylabel in zip(axes, SUMS, YLABELS):
            plot_panel(ax, table, f"{prefix}_q_e_au")
            ax.set_ylabel(ylabel)
            ax.spines["left"].set_position(("outward", 3))
            ax.spines["bottom"].set_position(("outward", 3))

        step = max(1, -(-len(table) // MAX_DATE_LABELS))
        bottom = axes[-1]
        bottom.set_xticks(table.index, minor=True)
        bottom.set_xticks(
            table.index[::step], table["date"][::step], rotation=45, ha="right"
        )
        # A full slot of room each side so the end markers are not clipped.
        bottom.set_xlim(-1, len(table))
        bottom.set_xlabel("Time")
        for ax in axes[:-1]:
            ax.tick_params(axis="x", which="both", length=0)
            ax.spines["bottom"].set_visible(False)

        handles = legend_handles(table)
        fig.legend(
            handles=handles,
            loc="upper center",
            ncols=len(handles),
            frameon=True,
            fancybox=True,
            framealpha=1,
            facecolor="#f7f6f3",
            edgecolor=GRID,
            borderpad=0.5,
            handletextpad=0.3,
            columnspacing=1.4,
            fontsize=7.5,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=1.6)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=300)
        plt.close(fig)
    return output_path


if __name__ == "__main__":
    FOLDER_NAME = "nn1120-4_pd_ceo2_000"
    INPUT_SUBFOLDER = "_reprocess"  # "" for the folder root
    FIT_SUBFOLDER = ""  # kinetic files sit in _reprocess itself since 2026-10-10

    result = collect(FOLDER_NAME, INPUT_SUBFOLDER, FIT_SUBFOLDER)
    out = plot(
        result,
        Path(config.get_path("data.figures", FOLDER_NAME, "carbonyl_density.tiff")),
    )
    print(f"Wrote {out}")
    columns = ["short", "date", "regime"] + [
        f"{prefix}_{key}"
        for prefix, _ in SUMS
        for key in ("segment", "q_e_au", "r^2", "note")
    ]
    with pd.option_context("display.max_rows", None, "display.width", 240):
        print(result[columns])
