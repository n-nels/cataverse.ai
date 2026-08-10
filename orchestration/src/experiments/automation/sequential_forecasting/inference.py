"""Leakage-safe cutoff-by-cutoff sequential inference."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .baselines import baseline_prediction
from .config import DEFAULT_ODE_TIMEOUT_SECONDS
from .data.adapter import build_examples_from_artifacts
from .data.contract import AREA_COLUMN, TIME_COLUMN
from .data.examples import FIT_VALID, SequentialExample
from .data.observations import flatten_monomer_rows
from .models.secondary_pfo import (
    ForecastResult,
    SecondaryPfoParameters,
    build_cutoff_forecast_with_fallback,
)


@dataclass(frozen=True)
class InferenceRecord:
    """One auditable prediction and forecast at a measurement cutoff."""

    experiment_id: str
    cutoff_id: str
    assignment: str | None
    cutoff_time_s: float
    final_time_s: float
    observation_count: int
    progress_group: str
    input_observation_times_s: tuple[float, ...]
    input_observation_area: tuple[float, ...]
    fit_status: str
    current_fit_available: tuple[bool, ...]
    rf_prediction: tuple[float, ...] | None
    rf_prediction_provenance: str | None
    csv_path: str | None
    json_path: str | None
    reference_status: str
    reference_provenance: str
    model_candidate: str
    prediction: tuple[float, ...] | None
    parameter_validation_status: str
    prediction_source: str
    fallback_reason: str | None
    curve_times_s: tuple[float, ...] | None
    curve_predicted_area: tuple[float, ...] | None
    curve_status: str
    error: str | None


@dataclass(frozen=True)
class InferenceArtifacts:
    """Loaded model-selection metadata and optional learned model."""

    manifest: dict[str, Any]
    model: Any | None


def load_inference_artifacts(model_dir: str | Path) -> InferenceArtifacts:
    """Load the persisted model-selection manifest and active model.

    RF-only selection intentionally has no active learned model. A learned
    candidate must have both a positive manifest selection and a model file.
    """
    model_path = Path(model_dir)
    manifest_path = model_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = manifest.get("selected_candidate")
    if selected == "rf_only" or not manifest.get("learned_model_selected", False):
        return InferenceArtifacts(manifest=manifest, model=None)

    active_model_path = model_path / "model.joblib"
    if not active_model_path.exists():
        raise FileNotFoundError(active_model_path)
    return InferenceArtifacts(
        manifest=manifest,
        model=joblib.load(active_model_path),
    )


def _progress_group(observation_fraction: float) -> str:
    """Return the stable progress label used by baseline evaluation."""
    if observation_fraction < 1.0 / 3.0:
        return "early"
    if observation_fraction < 2.0 / 3.0:
        return "middle"
    return "late"


def _validate_timeline(
    example: SequentialExample,
    times_s: np.ndarray,
    observed_area: np.ndarray,
) -> None:
    """Ensure the current example is an exact prefix of the full timeline."""
    if times_s.ndim != 1 or observed_area.ndim != 1 or times_s.size != observed_area.size:
        raise ValueError(f"Invalid full timeline for {example.experiment_id}")
    if times_s.size == 0 or not np.isfinite(times_s).all() or not np.isfinite(observed_area).all():
        raise ValueError(f"Full timeline is non-finite for {example.experiment_id}")
    if np.any(np.diff(times_s) < 0.0):
        raise ValueError(f"Full timeline is not chronological for {example.experiment_id}")
    prefix_count = example.observation_count
    if prefix_count > times_s.size:
        raise ValueError(f"Cutoff exceeds full timeline for {example.cutoff_id}")
    prefix_times = np.asarray(example.observation_times_s, dtype=float)
    prefix_area = np.asarray(example.observation_area, dtype=float)
    if prefix_times.size != prefix_count or prefix_area.size != prefix_count:
        raise ValueError(f"Example prefix length is inconsistent for {example.cutoff_id}")
    if not np.array_equal(times_s[:prefix_count], prefix_times):
        raise ValueError(f"Example prefix times do not match full timeline for {example.cutoff_id}")
    if not np.array_equal(observed_area[:prefix_count], prefix_area):
        raise ValueError(f"Example prefix areas do not match full timeline for {example.cutoff_id}")
    if example.cutoff_time_s != float(prefix_times[-1]):
        raise ValueError(f"Cutoff time does not match its prefix for {example.cutoff_id}")


def _prefix_safe_area(observed_area: np.ndarray, count: int) -> np.ndarray:
    """Keep future area values unavailable while retaining the known time grid."""
    safe_area = np.zeros_like(observed_area, dtype=float)
    safe_area[:count] = observed_area[:count]
    return safe_area


def _model_candidate(
    example: SequentialExample,
    model: Any | None,
    selected_candidate: str,
) -> tuple[SecondaryPfoParameters | None, str | None]:
    """Produce a learned candidate only after a valid current ODE fit."""
    if model is None or selected_candidate == "rf_only":
        return None, None
    if example.fit_status != FIT_VALID:
        return None, f"current_fit_{example.fit_status}"
    prediction = model.predict_parameters(example)
    if prediction.parameters is None:
        return None, f"model_prediction_{prediction.source}:{prediction.reason}"
    return prediction.parameters, None


def _meaningful_fallback_reason(
    result: ForecastResult,
    candidate_reason: str | None,
) -> str | None:
    """Remove unavailable-candidate noise while retaining actual failures."""
    reasons = [candidate_reason] if candidate_reason else []
    if result.fallback_reason:
        reasons.extend(
            part
            for part in result.fallback_reason.split("; ")
            if not part.endswith(":unavailable")
        )
    return "; ".join(reason for reason in reasons if reason) or None


def _inference_record(
    example: SequentialExample,
    result: ForecastResult,
    *,
    model_candidate: str,
    rf_prediction: SecondaryPfoParameters | None,
    fallback_reason: str | None,
) -> InferenceRecord:
    """Convert a forecast result into the persisted cutoff trace schema."""
    forecast = result.forecast
    if forecast is None:
        curve_status = "prediction_invalid"
        curve_times = None
        curve_area = None
    else:
        curve_status = "valid"
        curve_times = tuple(float(value) for value in forecast.times_s)
        curve_area = tuple(float(value) for value in forecast.predicted_area)
    return InferenceRecord(
        experiment_id=example.experiment_id,
        cutoff_id=example.cutoff_id,
        assignment=example.assignment,
        cutoff_time_s=example.cutoff_time_s,
        final_time_s=example.final_time_s,
        observation_count=example.observation_count,
        progress_group=_progress_group(example.observation_fraction),
        input_observation_times_s=example.observation_times_s,
        input_observation_area=example.observation_area,
        fit_status=example.fit_status,
        current_fit_available=example.current_fit_available,
        rf_prediction=(
            tuple(float(value) for value in rf_prediction.as_array())
            if rf_prediction is not None
            else None
        ),
        rf_prediction_provenance=example.rf_prediction_provenance,
        csv_path=example.csv_path,
        json_path=example.json_path,
        reference_status=example.reference_status,
        reference_provenance=example.reference_provenance,
        model_candidate=model_candidate,
        prediction=(
            tuple(float(value) for value in result.parameters.as_array())
            if result.parameters is not None
            else None
        ),
        parameter_validation_status=("valid" if result.parameters is not None else "invalid"),
        prediction_source=result.source,
        fallback_reason=fallback_reason,
        curve_times_s=curve_times,
        curve_predicted_area=curve_area,
        curve_status=curve_status,
        error=None if result.valid else fallback_reason,
    )


def run_sequential_inference(
    examples: tuple[SequentialExample, ...],
    observations_by_experiment: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    model: Any | None = None,
    model_manifest: dict[str, Any] | None = None,
    timeout_seconds: float = DEFAULT_ODE_TIMEOUT_SECONDS,
) -> tuple[InferenceRecord, ...]:
    """Generate an ordered, leakage-safe forecast trace for every cutoff."""
    if not examples:
        raise ValueError("At least one sequential example is required")
    selected_candidate = str(
        (model_manifest or {}).get("selected_candidate", "rf_only")
    )
    ordered_examples = tuple(
        sorted(examples, key=lambda item: (item.experiment_id, item.cutoff_time_s, item.cutoff_id))
    )
    previous_valid_by_experiment: dict[str, SecondaryPfoParameters] = {}
    last_cutoff_by_experiment: dict[str, float] = {}
    forecast_cache: dict[
        tuple[float, tuple[float, ...], tuple[float, ...]],
        tuple[np.ndarray, np.ndarray],
    ] = {}
    records: list[InferenceRecord] = []

    for example in ordered_examples:
        previous_cutoff = last_cutoff_by_experiment.get(example.experiment_id)
        if previous_cutoff is not None and example.cutoff_time_s <= previous_cutoff:
            raise ValueError(f"Cutoffs are not strictly chronological for {example.experiment_id}")
        last_cutoff_by_experiment[example.experiment_id] = example.cutoff_time_s

        if example.experiment_id not in observations_by_experiment:
            raise KeyError(f"Missing full observations for {example.experiment_id}")
        full_times, full_area = (
            np.asarray(observations_by_experiment[example.experiment_id][0], dtype=float),
            np.asarray(observations_by_experiment[example.experiment_id][1], dtype=float),
        )
        _validate_timeline(example, full_times, full_area)

        rf_result = baseline_prediction(example, "rf_only")
        candidate, candidate_reason = _model_candidate(
            example, model, selected_candidate
        )
        previous_valid = previous_valid_by_experiment.get(example.experiment_id)
        safe_area = _prefix_safe_area(full_area, example.observation_count)
        result = build_cutoff_forecast_with_fallback(
            full_times,
            safe_area,
            example.cutoff_time_s,
            candidate=candidate,
            previous_valid=previous_valid,
            rf_prediction=rf_result.parameters,
            final_time_s=example.final_time_s,
            timeout_seconds=timeout_seconds,
            forecast_cache=forecast_cache,
        )
        if result.source in {"sequential", "previous_valid"} and result.parameters is not None:
            previous_valid_by_experiment[example.experiment_id] = result.parameters
        fallback_reason = _meaningful_fallback_reason(result, candidate_reason)
        records.append(
            _inference_record(
                example,
                result,
                model_candidate=selected_candidate,
                rf_prediction=rf_result.parameters,
                fallback_reason=fallback_reason,
            )
        )
    return tuple(records)


def _load_observations(
    examples: tuple[SequentialExample, ...],
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Load flattened complete timelines used only as a known time grid."""
    observations: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for example in examples:
        if example.experiment_id in observations:
            continue
        if example.csv_path is None:
            raise ValueError(f"CSV provenance is missing for {example.experiment_id}")
        flattened, _ = flatten_monomer_rows(pd.read_csv(example.csv_path))
        timeline = flattened.loc[flattened[TIME_COLUMN] <= example.final_time_s]
        observations[example.experiment_id] = (
            timeline[TIME_COLUMN].to_numpy(dtype=float),
            timeline[AREA_COLUMN].to_numpy(dtype=float),
        )
    return observations


def _manifest(records: tuple[InferenceRecord, ...], artifacts: InferenceArtifacts) -> dict[str, Any]:
    """Summarize the inference trace without duplicating each prediction."""
    return {
        "selected_candidate": artifacts.manifest.get("selected_candidate", "rf_only"),
        "learned_model_loaded": artifacts.model is not None,
        "record_count": len(records),
        "experiment_count": len({record.experiment_id for record in records}),
        "assignment_counts": dict(Counter(record.assignment for record in records)),
        "prediction_source_counts": dict(Counter(record.prediction_source for record in records)),
        "curve_status_counts": dict(Counter(record.curve_status for record in records)),
        "fallback_count": sum(record.fallback_reason is not None for record in records),
    }


def run_inference(
    artifact_dir: str | Path,
    *,
    model_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    timeout_seconds: float | None = None,
) -> Path:
    """Run Phase 7 inference from persisted examples and model artifacts."""
    artifact_path = Path(artifact_dir)
    examples = build_examples_from_artifacts(artifact_path)
    model_path = Path(model_dir) if model_dir is not None else artifact_path / "sequential_model"
    artifacts = load_inference_artifacts(model_path)
    records = run_sequential_inference(
        examples,
        _load_observations(examples),
        model=artifacts.model,
        model_manifest=artifacts.manifest,
        timeout_seconds=(
            DEFAULT_ODE_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        ),
    )
    output_path = Path(output_dir) if output_dir is not None else artifact_path / "inference"
    output_path.mkdir(parents=True, exist_ok=True)
    with (output_path / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), default=str) + "\n")
    (output_path / "manifest.json").write_text(
        json.dumps(_manifest(records, artifacts), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return output_path
