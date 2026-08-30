"""Reading fitted kinetic parameters out of the peak-area CSVs.

One `<base>_CarbonylPeakArea.csv` per experiment, produced by `ir-spectro-node`
after the run. Each file holds the whole fit history - the observed sample has
2,120 rows: 20 peaks x 106 time points - and the graph stores one summary row
per peak.

Selection rule, carried over from the original pipeline: within each peak,
take the row with the largest `Time (s)`. That is the fit as of the end of the
experiment, which is the number a reader means by "the rate constant for this
run". No delta-window grouping.

Deliberately uses the standard library rather than pandas. The file is read
once, row by row, and the only operation is a max - pandas would add a heavy
dependency for a `for` loop, and its NaN handling actively gets in the way
(see `_number`).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

#: CSV header -> graph property. Carried over verbatim: these property names
#: are already in the database on 238 AdsParams nodes.
COLUMNS: dict[str, str] = {
    "Time (s)": "time_s",
    "pfo-sec_r^2": "pfo_sec_r2",
    "pfo-sec_rmse": "pfo_sec_rmse",
    "pfo-sec_k_a_s-1": "pfo_sec_k_a",
    "pfo-sec_k_a_stderr": "pfo_sec_k_a_stderr",
    "pfo-sec_q_e_au": "pfo_sec_q_e",
    "pfo-sec_q_e_stderr": "pfo_sec_q_e_stderr",
    "pfo-sec_k_s_s-1": "pfo_sec_k_s",
    "pfo-sec_k_s_stderr": "pfo_sec_k_s_stderr",
    "pfo-sec_k_p_s-1": "pfo_sec_k_p",
    "pfo-sec_k_p_stderr": "pfo_sec_k_p_stderr",
    "pfo-sec_q_inf_au": "pfo_sec_q_inf",
    "pfo-sec_q_inf_stderr": "pfo_sec_q_inf_stderr",
    "pfo-sec_q0_au": "pfo_sec_q0",
}

#: Peaks loaded into the graph. The observed CSV carries 20 - monomer_sum,
#: cluster_sum, and 18 individual wavenumbers - but only monomer_sum is
#: currently wanted. Widening this set needs no schema change: AdsParams is
#: already keyed on (base_name, peak_name).
LOADED_PEAKS = frozenset({"monomer_sum"})

SUFFIX = "_CarbonylPeakArea.csv"


def _number(raw: str | None) -> float | None:
    """Parse a CSV cell as a float, or None.

    Empty cells, non-numeric text, and NaN all become None. NaN matters: the
    fit columns are full of them where a parameter had no standard error, and
    Neo4j has no NaN - storing one either fails or produces a property that is
    not equal to itself, which quietly breaks every comparison against it.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return None if math.isnan(value) or math.isinf(value) else value


def csv_path_for(base_name: str, folder: Path) -> Path:
    return folder / f"{base_name}{SUFFIX}"


def load(base_name: str, folder: str | Path) -> list[dict[str, Any]]:
    """Fitted parameters for one experiment, one dict per loaded peak.

    Returns an empty list when the CSV is absent - normal for a run that was
    started and abandoned - or when it holds no rows for the wanted peaks.
    """
    path = csv_path_for(base_name, Path(folder))
    if not path.exists():
        return []

    best: dict[str, tuple[float, dict[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            peak = (row.get("Peak_Name") or "").strip()
            if peak not in LOADED_PEAKS:
                continue
            elapsed = _number(row.get("Time (s)"))
            if elapsed is None:
                continue
            if peak not in best or elapsed > best[peak][0]:
                best[peak] = (elapsed, row)

    return [
        {
            "peak_name": peak,
            **{prop: _number(row.get(column)) for column, prop in COLUMNS.items()},
        }
        for peak, (_, row) in sorted(best.items())
    ]


def load_all(base_names: list[str], root: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Fits for many experiments, keyed by base name.

    Each CSV sits beside its experiment's JSON, so the folder is found per
    experiment rather than assumed to be one directory.
    """
    root = Path(root)
    found: dict[str, list[dict[str, Any]]] = {}
    for base_name in base_names:
        for candidate in root.rglob(f"{base_name}{SUFFIX}"):
            rows = load(base_name, candidate.parent)
            if rows:
                found[base_name] = rows
            break
    return found
