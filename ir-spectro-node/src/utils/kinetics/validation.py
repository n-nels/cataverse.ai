"""Validate a KineticClassification detector against the ground-truth labels.

Recomputes classification from raw ``Time (s)`` / ``Cumulative_Peak_Area``
rows for ``Peak_Name == "cluster_sum"`` -- it never reads the ``classification``
column already baked into the source CSVs by a prior real-time run.

Correctness is defined under monotonic-once-triggered aggregation: a
``discontinuous``-labeled file is correct iff the detector fires
``discontinuous`` at *some* prefix of its trajectory; a ``continuous``-labeled
file is correct iff it never fires at any prefix. See docs/spec.md and
docs/prompt.md for the full definition.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.kinetic_fit_writer import CLASSIFIER, SEARCH_ROOT, WRITER

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"
MIN_POINTS = 4

# The two known transient false positives in nn1120-3_pd_ceo2_003 fire for at
# most 2 consecutive prefixes before reverting (...-097: runs of 1 and 2;
# ...-115: runs of 1 and 1). Requiring 3 consecutive "discontinuous" prefixes
# before latching sits just above that measured noise ceiling.
REQUIRED_CONSECUTIVE_FIRES = 3


@dataclass
class FileResult:
    file: str
    folder: str
    label: str
    predicted_ever_fires: bool
    correct: bool
    n_points: int
    error: str | None = None


@dataclass
class ValidationReport:
    results: list[FileResult] = field(default_factory=list)

    @property
    def n_total(self) -> int:
        return len(self.results)

    @property
    def n_correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    def mismatches(self) -> list[FileResult]:
        return [r for r in self.results if not r.correct]

    def by_folder(self) -> dict[str, tuple[int, int]]:
        out: dict[str, list[int]] = {}
        for r in self.results:
            out.setdefault(r.folder, [0, 0])
            out[r.folder][1] += 1
            if r.correct:
                out[r.folder][0] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    def confusion(self) -> dict[str, int]:
        tp = fn = tn = fp = 0
        for r in self.results:
            if r.label == "discontinuous":
                if r.predicted_ever_fires:
                    tp += 1
                else:
                    fn += 1
            else:
                if r.predicted_ever_fires:
                    fp += 1
                else:
                    tn += 1
        return {"tp": tp, "fn": fn, "tn": tn, "fp": fp}

    def print_summary(self) -> None:
        print(f"Overall: {self.n_correct}/{self.n_total} correct")
        conf = self.confusion()
        print(
            f"Discontinuous: {conf['tp']} correctly fired, {conf['fn']} missed | "
            f"Continuous: {conf['tn']} correctly quiet, {conf['fp']} false positives"
        )
        for folder, (correct, total) in sorted(self.by_folder().items()):
            marker = "" if correct == total else "  <-- mismatches here"
            print(f"  {folder}: {correct}/{total}{marker}")
        mismatches = self.mismatches()
        if mismatches:
            print(f"\n{len(mismatches)} mismatch(es):")
            for r in mismatches:
                tag = "MISSED" if r.label == "discontinuous" else "FALSE_POSITIVE"
                err = f" (error: {r.error})" if r.error else ""
                print(f"  [{tag}] {r.folder}/{r.file} (label={r.label}){err}")


def _cluster_sum_trajectory(csv_path: Path) -> tuple[list[float], list[float]]:
    df = pd.read_csv(csv_path)
    df = WRITER.utils.prepare_peak_area_df(df)
    cluster = df[df["Peak_Name"] == "cluster_sum"].sort_values("Time (s)")
    time_s = cluster["Time (s)"].to_numpy(dtype=float)
    intensity = cluster["Cumulative_Peak_Area"].to_numpy(dtype=float)
    return time_s, intensity


def ever_fires(
    classify_fn: Callable[..., dict[str, Any]],
    time_s,
    intensity,
    *,
    min_points: int = MIN_POINTS,
    required_consecutive: int = REQUIRED_CONSECUTIVE_FIRES,
) -> bool:
    """Sweep growing prefixes; True once 'discontinuous' fires on
    ``required_consecutive`` consecutive prefixes.

    This is the monotonic-once-triggered aggregation policy applied to a full
    offline trajectory, with a sustained-confirmation guard: the real-time
    pipeline latches only after the detector has fired on
    ``required_consecutive`` consecutive incoming data points in a row (never
    reverting once latched), rather than on the very first fire. A single
    isolated fire, or a run shorter than ``required_consecutive``, does not
    latch.

    ``classify_fn`` is any ``classify_trajectory``-shaped callable (i.e.
    ``KineticClassification.classify_trajectory`` or
    ``.classify_trajectory_sustained_rise``, bound to a classifier instance)
    -- swapping it is how a new candidate detector is run through this same
    harness without duplicating the sweep/aggregation logic.
    """
    n = len(time_s)
    consecutive = 0
    for k in range(min_points, n + 1):
        result = classify_fn(time_s[:k], intensity[:k])
        if result.get("classification") == "discontinuous":
            consecutive += 1
            if consecutive >= required_consecutive:
                return True
        else:
            consecutive = 0
    return False


def run_validation(
    ground_truth_path: Path = GROUND_TRUTH_PATH,
    *,
    classify_fn: Callable[..., dict[str, Any]] | None = None,
    search_root: Path = SEARCH_ROOT,
) -> ValidationReport:
    classify_fn = classify_fn if classify_fn is not None else CLASSIFIER.classify_trajectory
    entries = json.loads(Path(ground_truth_path).read_text())

    report = ValidationReport()
    for entry in entries:
        csv_path = search_root / entry["folder"] / entry["file"]
        try:
            time_s, intensity = _cluster_sum_trajectory(csv_path)
            fired = ever_fires(classify_fn, time_s, intensity)
            error = None
            n_points = len(time_s)
        except Exception as exc:  # noqa: BLE001 - record and keep going
            fired = False
            error = str(exc)
            n_points = 0

        correct = (entry["label"] == "discontinuous") == fired
        report.results.append(
            FileResult(
                file=entry["file"],
                folder=entry["folder"],
                label=entry["label"],
                predicted_ever_fires=fired,
                correct=correct,
                n_points=n_points,
                error=error,
            )
        )
    return report


if __name__ == "__main__":
    report = run_validation()
    report.print_summary()
