"""Validate the nucleation detector against the ground-truth labels.

Recomputes classification from raw ``Time (s)`` / ``Cumulative_Peak_Area``
rows (``classification.nucleation_trajectory``: Peak_1988 + ``monomer_sum``)
-- it never reads the ``classification`` column already baked into any CSV.

Correctness is defined under monotonic-once-triggered aggregation: a
``discontinuous``-labeled file is correct iff the detector fires
``discontinuous`` at *some* prefix of its trajectory; a ``continuous``-labeled
file is correct iff it never fires at any prefix. The sweep itself is
``classification.latch_sweep``, shared with the written ``classification``
column. See docs/spec_nuc-clf.md for the full definition.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.kinetics.classification import (
    REQUIRED_CONSECUTIVE_FIRES,
    classify_nucleation,
    latch_sweep,
    nucleation_trajectory,
)
from src.utils.kinetics.writer import SEARCH_ROOT

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"
MIN_POINTS = 4


@dataclass
class FileResult:
    file: str
    folder: str
    label: str
    basis: str
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

    def by_basis(self) -> dict[str, tuple[int, int]]:
        out: dict[str, list[int]] = {}
        for r in self.results:
            out.setdefault(r.basis, [0, 0])
            out[r.basis][1] += 1
            if r.correct:
                out[r.basis][0] += 1
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
        print("By ground-truth basis:")
        for basis, (correct, total) in sorted(self.by_basis().items()):
            print(f"  {basis}: {correct}/{total}")
        mismatches = self.mismatches()
        if mismatches:
            print(f"\n{len(mismatches)} mismatch(es):")
            for r in mismatches:
                tag = "MISSED" if r.label == "discontinuous" else "FALSE_POSITIVE"
                err = f" (error: {r.error})" if r.error else ""
                print(
                    f"  [{tag}] {r.folder}/{r.file} (label={r.label}, "
                    f"basis={r.basis}){err}"
                )


def ever_fires(
    classify_fn: Callable[..., dict[str, Any]],
    time_s,
    intensity,
    *,
    min_points: int = MIN_POINTS,
    required_consecutive: int = REQUIRED_CONSECUTIVE_FIRES,
) -> bool:
    """True once ``discontinuous`` fires on ``required_consecutive`` consecutive
    growing prefixes (``classification.latch_sweep``)."""
    latch = latch_sweep(
        classify_fn,
        time_s,
        intensity,
        min_points=min_points,
        required_consecutive=required_consecutive,
    )
    return latch.n_points is not None


def run_validation(
    ground_truth_path: Path = GROUND_TRUTH_PATH,
    *,
    classify_fn: Callable[..., dict[str, Any]] | None = None,
    search_root: Path = SEARCH_ROOT,
    required_consecutive: int = REQUIRED_CONSECUTIVE_FIRES,
    input_subfolder: str | None = None,
    folders: list[str] | None = None,
    trajectory_fn: Callable[[pd.DataFrame], tuple[Any, Any]] | None = None,
) -> ValidationReport:
    """Score ``classify_fn`` against ``ground_truth.json``.

    Args:
        classify_fn: Detector to sweep. ``None`` = ``classify_nucleation``,
            the one the writer uses.
        input_subfolder: Read each file from ``<folder>/<input_subfolder>/``
            (e.g. ``"_reprocess"``) instead of the live dataset folder.
        folders: Only score ground-truth entries in these dataset folders.
        trajectory_fn: Build the swept ``(time_s, intensity)`` from the area
            frame. ``None`` = ``nucleation_trajectory``. ``latch_sweep`` only
            slices ``[:k]``, so any row-aligned array works.

    A file that errors (e.g. no area CSV) is scored wrong, never as a quiet
    ``continuous``.
    """
    classify_fn = classify_fn if classify_fn is not None else classify_nucleation
    trajectory_fn = (
        trajectory_fn if trajectory_fn is not None else nucleation_trajectory
    )
    entries = json.loads(Path(ground_truth_path).read_text())

    report = ValidationReport()
    for entry in entries:
        if folders is not None and entry["folder"] not in folders:
            continue
        folder_path = search_root / entry["folder"]
        if input_subfolder:
            folder_path = folder_path / input_subfolder
        csv_path = folder_path / entry["file"]
        try:
            time_s, intensity = trajectory_fn(pd.read_csv(csv_path))
            fired = ever_fires(
                classify_fn,
                time_s,
                intensity,
                required_consecutive=required_consecutive,
            )
            error = None
            n_points = len(time_s)
        except Exception as exc:  # noqa: BLE001 - record and keep going
            fired = False
            error = str(exc)
            n_points = 0

        correct = error is None and (entry["label"] == "discontinuous") == fired
        report.results.append(
            FileResult(
                file=entry["file"],
                folder=entry["folder"],
                label=entry["label"],
                basis=entry.get("basis", ""),
                predicted_ever_fires=fired,
                correct=correct,
                n_points=n_points,
                error=error,
            )
        )
    return report


@dataclass
class SpikeResult:
    file: str
    folder: str
    label: bool
    predicted: bool
    correct: bool
    error: str | None = None


def run_spike_validation(
    ground_truth_path: Path = GROUND_TRUTH_PATH,
    *,
    search_root: Path = SEARCH_ROOT,
    input_subfolder: str | None = "_reprocess",
    folders: list[str] | None = None,
) -> list[SpikeResult]:
    """Score the cluster_sum spike detector (``segments.detect_spike``).

    Only entries carrying a boolean ``spike`` are scored. The prediction is
    the ``spike_detected`` feature of ``segments.SEGMENT_WRITER.features``,
    so a file the nucleation detector calls continuous predicts no spike. A
    file that errors is scored wrong.
    """
    from src.utils.kinetics.segments import SEGMENT_WRITER

    results: list[SpikeResult] = []
    for entry in json.loads(Path(ground_truth_path).read_text()):
        if "spike" not in entry:
            continue
        if folders is not None and entry["folder"] not in folders:
            continue
        folder_path = search_root / entry["folder"]
        if input_subfolder:
            folder_path = folder_path / input_subfolder
        try:
            features = SEGMENT_WRITER.features(
                pd.read_csv(folder_path / entry["file"]),
                entry["base_name"],
                min_points=MIN_POINTS,
            )
            predicted = features.get("spike_detected") in (True, 1)
            error = None
        except Exception as exc:  # noqa: BLE001 - record and keep going
            predicted, error = False, str(exc)
        label = bool(entry["spike"])
        results.append(
            SpikeResult(
                file=entry["file"],
                folder=entry["folder"],
                label=label,
                predicted=predicted,
                correct=error is None and predicted == label,
                error=error,
            )
        )
    return results


def print_spike_summary(results: list[SpikeResult]) -> None:
    n_correct = sum(r.correct for r in results)
    n_spikes = sum(r.label for r in results)
    print(
        f"Spike: {n_correct}/{len(results)} labeled files correct "
        f"({n_spikes} labeled spike)"
    )
    for r in results:
        if not r.correct:
            tag = "MISSED" if r.label else "FALSE_POSITIVE"
            err = f" (error: {r.error})" if r.error else ""
            print(f"  [{tag}] {r.folder}/{r.file}{err}")


if __name__ == "__main__":
    report = run_validation()
    report.print_summary()
