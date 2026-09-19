"""Shared structured prediction result for sequential candidate models."""

from __future__ import annotations

from dataclasses import dataclass

from .models.secondary_pfo import SecondaryPfoParameters


@dataclass(frozen=True)
class ModelPrediction:
    """Structured candidate-model prediction result."""

    parameters: SecondaryPfoParameters | None
    source: str
    reason: str | None
