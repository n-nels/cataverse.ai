"""Experiment manifest loading and validation.

A manifest is a YAML file that defines the bounds of an autonomous campaign.
The harness refuses to run without a valid manifest. Hyperparameters declared
in the manifest are advisory (a starting point); the agent may search beyond
them. The harness logs (not rejects) undeclared or out-of-range params.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Defaults from spec.md "Default Resource Limits" and "Keep / Discard Rule".
DEFAULT_MAX_TRIALS = 30
DEFAULT_MAX_WALL_CLOCK_MINUTES = 120
DEFAULT_MAX_TEST_FINALISTS = 3
DEFAULT_MAX_RETRIES = 2
DEFAULT_PER_TRIAL_TIMEOUT_MINUTES = 10
DEFAULT_MIN_IMPROVEMENT = 0.005
DEFAULT_PRIMARY_METRIC = "validation_avg_rmse"
DEFAULT_SEARCH_METHOD = "random"
CANONICAL_SEED = 42

REQUIRED_FIELDS = (
    "experiment_id",
    "description",
    "model_name",
    "baseline_experiment",
    "split_seed",
    "primary_metric",
    "search_method",
    "allowed_hyperparameters",
    "maximum_trial_count",
    "maximum_wall_clock_minutes",
    "maximum_test_finalists",
    "artifact_output_location",
)


class ManifestError(ValueError):
    """Raised when a manifest is missing required fields or is malformed."""


@dataclass
class HyperparameterSpec:
    name: str
    type: str  # "numeric" or "categorical"
    range: tuple[float, float] | None = None
    choices: list[Any] | None = None

    def __post_init__(self) -> None:
        if self.type == "numeric":
            if self.range is None or len(self.range) != 2:
                raise ManifestError(
                    f"hyperparameter {self.name!r} is numeric but has no valid range"
                )
            lo, hi = self.range
            if lo > hi:
                raise ManifestError(
                    f"hyperparameter {self.name!r} range low {lo} > high {hi}"
                )
        elif self.type == "categorical":
            if not self.choices:
                raise ManifestError(
                    f"hyperparameter {self.name!r} is categorical but has no choices"
                )
        else:
            raise ManifestError(
                f"hyperparameter {self.name!r} has unsupported type {self.type!r} "
                "(expected 'numeric' or 'categorical')"
            )

    def contains(self, value: Any) -> bool:
        if self.type == "numeric":
            lo, hi = self.range  # type: ignore[misc]
            return lo <= value <= hi
        return value in self.choices  # type: ignore[union-attr]


@dataclass
class Manifest:
    experiment_id: str
    description: str
    model_name: str
    baseline_experiment: str
    split_seed: int
    primary_metric: str
    search_method: str
    allowed_hyperparameters: list[HyperparameterSpec]
    maximum_trial_count: int
    maximum_wall_clock_minutes: int
    maximum_test_finalists: int
    artifact_output_location: str
    # Optional / defaulted fields
    dataset_version: str | None = None
    split_identifier: str | None = None
    per_trial_timeout_minutes: int = DEFAULT_PER_TRIAL_TIMEOUT_MINUTES
    minimum_improvement_threshold: float = DEFAULT_MIN_IMPROVEMENT
    maximum_retries: int = DEFAULT_MAX_RETRIES
    raw: dict | None = None  # original parsed dict, for artifact writing

    def hyperparameter_names(self) -> set[str]:
        return {hp.name for hp in self.allowed_hyperparameters}

    def spec_for(self, name: str) -> HyperparameterSpec:
        for hp in self.allowed_hyperparameters:
            if hp.name == name:
                return hp
        raise ManifestError(f"hyperparameter {name!r} not declared in manifest")

    def is_approved_params(self, params: dict) -> tuple[bool, str]:
        """Return (ok, reason). Advisory check — logs but does not reject.

        Per spec, declared hyperparameters are advisory (a starting point), not
        binding. The agent may search beyond them. This method returns (True, "")
        always, but includes a warning reason when params are undeclared or
        out-of-range so the caller can log it for traceability.
        """
        warnings = []
        for key, value in params.items():
            if key not in self.hyperparameter_names():
                warnings.append(f"parameter {key!r} not declared in manifest (advisory)")
                continue
            spec = self.spec_for(key)
            if not spec.contains(value):
                warnings.append(f"parameter {key!r} value {value!r} outside declared bounds (advisory)")
        return True, "; ".join(warnings)


def _parse_hyperparameters(raw: Any) -> list[HyperparameterSpec]:
    if not isinstance(raw, list):
        raise ManifestError("allowed_hyperparameters must be a list")
    specs: list[HyperparameterSpec] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ManifestError(f"allowed_hyperparameters[{i}] must be a mapping")
        name = entry.get("name")
        if not name:
            raise ManifestError(f"allowed_hyperparameters[{i}] missing 'name'")
        htype = entry.get("type")
        rng = entry.get("range")
        choices = entry.get("choices")
        if rng is not None:
            rng = tuple(rng)
        specs.append(HyperparameterSpec(name=name, type=htype, range=rng, choices=choices))
    return specs


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a manifest YAML file."""
    p = Path(path)
    if not p.exists():
        raise ManifestError(f"manifest not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")

    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ManifestError(f"manifest missing required fields: {missing}")

    seed = int(raw["split_seed"])
    if seed != CANONICAL_SEED:
        raise ManifestError(
            f"split_seed must be the canonical seed {CANONICAL_SEED} (got {seed}); "
            "the split seed is ETL-protected and may not be overridden"
        )

    return Manifest(
        experiment_id=str(raw["experiment_id"]),
        description=str(raw["description"]),
        model_name=str(raw["model_name"]),
        baseline_experiment=str(raw["baseline_experiment"]),
        split_seed=seed,
        primary_metric=str(raw.get("primary_metric", DEFAULT_PRIMARY_METRIC)),
        search_method=str(raw.get("search_method", DEFAULT_SEARCH_METHOD)),
        allowed_hyperparameters=_parse_hyperparameters(raw["allowed_hyperparameters"]),
        maximum_trial_count=int(raw["maximum_trial_count"]),
        maximum_wall_clock_minutes=int(raw["maximum_wall_clock_minutes"]),
        maximum_test_finalists=int(raw["maximum_test_finalists"]),
        artifact_output_location=str(raw["artifact_output_location"]),
        dataset_version=raw.get("dataset_version"),
        split_identifier=raw.get("split_identifier"),
        per_trial_timeout_minutes=int(
            raw.get("per_trial_timeout_minutes", DEFAULT_PER_TRIAL_TIMEOUT_MINUTES)
        ),
        minimum_improvement_threshold=float(
            raw.get("minimum_improvement_threshold", DEFAULT_MIN_IMPROVEMENT)
        ),
        maximum_retries=int(raw.get("maximum_retries", DEFAULT_MAX_RETRIES)),
        raw=raw,
    )