"""Elapsed-time-gated RF/current-ODE blend, the second sequential candidate.

Baseline C (`baselines.py`) blends the RF prediction and the current ODE fit
with one fixed weight across every cutoff. The Phase 6 evidence shows the
current ODE fit is far more accurate than the RF prediction late in an
experiment and less accurate early, so a single fixed weight cannot exploit
that pattern. This candidate instead learns one blend weight per
elapsed-time-fraction bin (`elapsed_time_fraction` only depends on the known
final time, per spec.md #5, so it is legitimate cutoff-time information).

`k_p` must satisfy `0 <= k_p <= k_a`. A convex combination
`w * a + (1 - w) * b` of two vectors that already each satisfy that
inequality also satisfies it for any shared weight `w`, so `k_a` and `k_p`
always use the same weight within a bin. Interval-bounded parameters
(`q_e`, `k_s`, `q_inf`) do not have this coupling risk and are allowed
independent weights. Every blended vector is still re-validated before use;
an invalid result reports its reason rather than being silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

import numpy as np
import pandas as pd

from .data.contract import TARGET_COLUMNS
from .data.examples import FIT_VALID, SequentialExample
from .model_prediction import ModelPrediction
from .models.secondary_pfo import SecondaryPfoParameters, validate_secondary_pfo_parameters


MODEL_NAME = "gated_blend"
LEARNED_TARGET_COLUMNS = TARGET_COLUMNS[:-1]
DEFAULT_BIN_COUNTS = (1, 2, 3, 4)

# Parameters that must share one blend weight to preserve k_p <= k_a; the
# remaining learned parameters only have independent interval bounds.
WEIGHT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("pfo-sec_k_a_s-1", "pfo-sec_k_p_s-1"),
    ("pfo-sec_q_e_au",),
    ("pfo-sec_k_s_s-1",),
    ("pfo-sec_q_inf_au",),
)


def _group_key(group: tuple[str, ...]) -> str:
    """Return a stable manifest/dict key for one weight group."""
    return "+".join(group)


def bin_edges(bin_count: int) -> tuple[float, ...]:
    """Return interior [0, 1] cut points for `bin_count` equal-width bins."""
    if bin_count < 1:
        raise ValueError("bin_count must be positive")
    return tuple(index / bin_count for index in range(1, bin_count))


def bin_index(elapsed_time_fraction: float, edges: tuple[float, ...]) -> int:
    """Return the bin index for one elapsed-time fraction at cutoff time."""
    fraction = min(max(float(elapsed_time_fraction), 0.0), 1.0)
    index = 0
    for edge in edges:
        if fraction < edge:
            break
        index += 1
    return index


@dataclass(frozen=True)
class FittedGatedBlendModel:
    """One RF/current-ODE blend weight per parameter group and time bin."""

    bin_edges: tuple[float, ...]
    weights: Mapping[str, tuple[float, ...]]
    bin_count: int

    def predict_parameters(self, example: SequentialExample) -> ModelPrediction:
        """Blend the RF prediction and current fit using the cutoff's bin."""
        if example.rf_prediction is None or len(example.rf_prediction) != len(TARGET_COLUMNS):
            return ModelPrediction(None, "invalid", "rf_prediction_unavailable")
        if example.fit_status != FIT_VALID or any(
            value is None for value in example.current_fit_values
        ):
            return ModelPrediction(None, "invalid", f"current_fit_{example.fit_status}")

        rf = np.asarray(example.rf_prediction, dtype=float)
        ode = np.asarray([float(value) for value in example.current_fit_values], dtype=float)
        bucket = bin_index(example.elapsed_time_fraction, self.bin_edges)
        blended = rf.copy()
        for group in WEIGHT_GROUPS:
            weight = self.weights[_group_key(group)][bucket]
            for name in group:
                position = TARGET_COLUMNS.index(name)
                blended[position] = (1.0 - weight) * rf[position] + weight * ode[position]
        blended[-1] = float(example.q_0)

        try:
            parameters = SecondaryPfoParameters.from_values(blended.tolist())
            validate_secondary_pfo_parameters(parameters)
        except (ValueError, TypeError, FloatingPointError) as error:
            return ModelPrediction(None, "invalid", str(error))
        return ModelPrediction(parameters, MODEL_NAME, None)


def _sample_weights(examples: tuple[SequentialExample, ...]) -> np.ndarray:
    """Weight cutoffs so every experiment contributes equal total weight."""
    counts = pd.Series(example.experiment_id for example in examples).value_counts()
    return np.asarray(
        [1.0 / float(counts[example.experiment_id]) for example in examples], dtype=float
    )


def _fit_group_weight(
    training: tuple[SequentialExample, ...],
    group: tuple[str, ...],
    edges: tuple[float, ...],
) -> tuple[float, ...]:
    """Fit one clipped least-squares blend weight per bin for one group."""
    positions = [TARGET_COLUMNS.index(name) for name in group]
    buckets = np.asarray(
        [bin_index(example.elapsed_time_fraction, edges) for example in training]
    )
    sample_weight = _sample_weights(training)
    rf_values = np.asarray([example.rf_prediction for example in training], dtype=float)
    ode_values = np.asarray(
        [[float(value) for value in example.current_fit_values] for example in training],
        dtype=float,
    )
    reference_values = np.asarray(
        [example.reference_target for example in training], dtype=float
    )

    weights: list[float] = []
    bin_count = len(edges) + 1
    for bucket in range(bin_count):
        mask = buckets == bucket
        if not mask.any():
            weights.append(0.5)
            continue
        predictor = (ode_values[mask][:, positions] - rf_values[mask][:, positions]).reshape(-1)
        target = (reference_values[mask][:, positions] - rf_values[mask][:, positions]).reshape(-1)
        repeated_weight = np.repeat(sample_weight[mask], len(positions))
        denominator = float(np.sum(repeated_weight * predictor**2))
        if denominator <= 0.0:
            weights.append(0.5)
            continue
        slope = float(np.sum(repeated_weight * predictor * target) / denominator)
        weights.append(float(np.clip(slope, 0.0, 1.0)))
    return tuple(weights)


def fit_gated_blend_model(
    examples: tuple[SequentialExample, ...],
    *,
    bin_count: int,
) -> FittedGatedBlendModel:
    """Fit per-bin blend weights using training, fit-valid examples only."""
    training = tuple(
        example
        for example in examples
        if example.assignment == "train"
        and example.fit_status == FIT_VALID
        and example.rf_prediction is not None
        and all(value is not None for value in example.current_fit_values)
    )
    if not training:
        raise ValueError("Gated-blend model requires fit-valid training examples")
    edges = bin_edges(bin_count)
    weights = {
        _group_key(group): _fit_group_weight(training, group, edges) for group in WEIGHT_GROUPS
    }
    return FittedGatedBlendModel(bin_edges=edges, weights=weights, bin_count=bin_count)


def fingerprint_training_examples(examples: tuple[SequentialExample, ...]) -> str:
    """Fingerprint the fit-valid training subset used to learn blend weights."""
    payload = "\n".join(
        f"{example.experiment_id}|{example.cutoff_id}"
        for example in examples
        if example.assignment == "train" and example.fit_status == FIT_VALID
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
