"""Scratch pad: monomer_sum equilibrium capacity ``q_e`` per measurement.

Standalone, no CLI -- edit the constants in ``__main__``. Reads the segment
fits written by ``scripts\\run_kinetics_fit.py --folder <folder>`` (default
``--mode segments``) from ``<data.peak_fit>/<folder>/<INPUT_SUBFOLDER>/
<FIT_SUBFOLDER>/*_CarbonylKineticParams.csv``.

Per measurement, ``q_e`` comes from the **first** monomer_sum segment (the
smallest ``t_start_s``), i.e. before nucleation when there is nucleation:

- discontinuous: ``supersaturation``; continuous/unclassified: ``adsorption``;
- the column follows that row's model: ``pfo_q_e_au`` for pfo,
  ``pfo-sec_q_e_au`` for secondary_pfo. Today both monomer_sum segments are
  secondary_pfo (spec-working.md §2), so every point is ``pfo-sec_q_e_au``.

Only reference samples are kept: ``filename_flags.is_reference`` is true in
``<data.exp_params>/<folder>/<measurement>_expParams.json``. A measurement
without that JSON is dropped and listed.

The x axis ("Time") is evenly spaced: one slot per kept params file in sorted
(= time) order, not proportional to time. Every slot gets a tick; at most
``MAX_DATE_LABELS`` are labelled with the measurement's mm-dd date. Missing
fits keep their slot (dotted line) and are listed; ``q_e == 0`` (pinned at
the bound) is drawn hollow. Colour is the regime; there is no legend or title.
Output: ``<data.figures>/<folder>/scratch_monomer_q_e.png``.
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

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.kinetics.segments import PARAMS_SUFFIX
from src.utils.kinetics.writer import SEARCH_ROOT

EXP_PARAMS_SUFFIX = "_expParams.json"
SUM_NAME = "monomer_sum"
Q_E_COLUMN = {"pfo": "pfo_q_e_au", "secondary_pfo": "pfo-sec_q_e_au"}
FIGSIZE = (4, 3)  # inches: single journal column
MAX_DATE_LABELS = 6  # x ticks sit on every measurement; at most this many dated
REGIME_COLORS = {
    "continuous": "tab:green",
    "discontinuous": "tab:red",
    "unclassified": "tab:grey",
}


def first_segment_q_e(params_path: Path) -> dict:
    """``q_e`` of the first monomer_sum segment of one params file."""
    measurement = params_path.name.removesuffix(str(PARAMS_SUFFIX))
    row = {
        "Measurement": measurement,
        "short": measurement.rsplit("_", 1)[-1],
        "date": f"{measurement[4:6]}-{measurement[6:8]}",  # YYYYMMDD_... -> mm-dd
    }
    params = pd.read_csv(params_path)
    rows = params[params["Peak_Name"] == SUM_NAME].sort_values("t_start_s")
    if rows.empty:
        return {**row, "q_e_au": np.nan, "note": f"no {SUM_NAME} rows"}
    record = rows.iloc[0]
    column = Q_E_COLUMN.get(record["model"])
    q_e = float(record[column]) if column else np.nan
    return {
        **row,
        "regime": record["regime"],
        "segment": record["segment"],
        "model": record["model"],
        "n_points": record["n_points"],
        "r^2": record["r^2"],
        "q_e_au": q_e,
        "note": "" if np.isfinite(q_e) else "no fit",
    }


def is_reference(folder_name: str, measurement: str) -> bool | None:
    """``filename_flags.is_reference`` from the expParams JSON; None if missing."""
    json_path = Path(
        config.get_path(
            "data.exp_params", folder_name, f"{measurement}{EXP_PARAMS_SUFFIX}"
        )
    )
    if not json_path.exists():
        return None
    with json_path.open() as handle:
        flags = json.load(handle).get("filename_flags", {})
    return bool(flags.get("is_reference", False))


def collect(folder_name: str, input_subfolder: str, fit_subfolder: str) -> pd.DataFrame:
    """First-segment ``q_e`` of every reference measurement of one dataset."""
    source = SEARCH_ROOT / folder_name / input_subfolder / fit_subfolder
    files = sorted(source.glob(f"*{PARAMS_SUFFIX}"))
    if not files:
        raise FileNotFoundError(f"no *{PARAMS_SUFFIX} in {source}")
    kept: list[Path] = []
    no_json: list[str] = []
    for params_path in files:
        measurement = params_path.name.removesuffix(str(PARAMS_SUFFIX))
        flag = is_reference(folder_name, measurement)
        if flag is None:
            no_json.append(measurement)
        elif flag:
            kept.append(params_path)
    print(f"{len(kept)}/{len(files)} measurements are references")
    if no_json:
        print(f"dropped, no {EXP_PARAMS_SUFFIX}: {', '.join(no_json)}")
    if not kept:
        raise FileNotFoundError(f"no reference measurements in {source}")
    table = pd.DataFrame([first_segment_q_e(p) for p in kept])
    table.index.name = "index"
    return table


def plot(table: pd.DataFrame, output_path: Path) -> Path:
    """q_e per measurement, evenly spaced, with every ``step``-th date labelled."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for regime, color in REGIME_COLORS.items():
        sub = table[table["regime"] == regime]
        if sub.empty:
            continue
        pinned = sub["q_e_au"] == 0
        ax.plot(sub.index[~pinned], sub["q_e_au"][~pinned], "o", color=color, ms=4)
        if pinned.any():
            ax.plot(
                sub.index[pinned],
                sub["q_e_au"][pinned],
                "o",
                mfc="none",
                color=color,
                ms=4,
            )
    for i in table[table["q_e_au"].isna()].index:
        ax.axvline(i, color="tab:grey", lw=0.6, ls=":")

    step = max(1, -(-len(table) // MAX_DATE_LABELS))
    ax.set_xticks(table.index, minor=True)
    ax.set_xticks(table.index[::step], table["date"][::step], rotation=45, ha="right")
    ax.set_xlim(-0.5, len(table) - 0.5)
    ax.set_xlabel("Time")
    ax.set_ylabel("Monomer Density (a.u.)")
    fig.tight_layout()
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
        Path(config.get_path("data.figures", FOLDER_NAME, "scratch_monomer_q_e.png")),
    )
    print(f"Wrote {out}")
    columns = [
        "short",
        "date",
        "regime",
        "segment",
        "model",
        "n_points",
        "r^2",
        "q_e_au",
        "note",
    ]
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(result[columns])
