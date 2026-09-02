"""Reading the hand-authored knowledge YAML.

Unlike the data graph, whose source is instrument output on the share drive,
this is written by hand and lives in the repo at `graph-node/knowledge/`. It
changes when Nick edits it, not when an experiment finishes.

Five files, each described in `original/knowledge_graph_instructions.txt`:

    concepts.yaml          the concept vocabulary, plus its subtype hierarchy
    species.yaml           chemical species, keyed on formula
    py_functions.yaml      the orchestration API, as documented signatures
    model_parameters.yaml  one kinetic model and its fitted parameters
    mappings.yaml          how the above connect, and how they attach to data
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: Default location, relative to the package root.
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "knowledge"

FILES = {
    "concepts": "concepts.yaml",
    "species": "species.yaml",
    "py_functions": "py_functions.yaml",
    "model_parameters": "model_parameters.yaml",
    "mappings": "mappings.yaml",
}


class KnowledgeSourceError(Exception):
    """The knowledge YAML could not be read."""


@dataclass(frozen=True)
class KnowledgeSource:
    concepts: list[dict[str, Any]]
    species: list[dict[str, Any]]
    py_functions: list[dict[str, Any]]
    model: dict[str, Any]
    parameters: list[dict[str, Any]]
    mappings: dict[str, Any]

    @property
    def model_name(self) -> str:
        return self.model["name"]


def load(root: str | Path | None = None) -> KnowledgeSource:
    """Read all five files. Raises if any is missing or malformed."""
    root = Path(root) if root is not None else DEFAULT_ROOT
    raw: dict[str, Any] = {}
    for key, filename in FILES.items():
        path = root / filename
        try:
            raw[key] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KnowledgeSourceError(f"missing {path}") from exc
        except yaml.YAMLError as exc:
            raise KnowledgeSourceError(f"{filename}: {exc}") from exc

    model_file = raw["model_parameters"] or {}
    if "model" not in model_file or "parameters" not in model_file:
        raise KnowledgeSourceError(
            "model_parameters.yaml must define both `model` and `parameters`"
        )

    return KnowledgeSource(
        concepts=raw["concepts"] or [],
        species=raw["species"] or [],
        py_functions=raw["py_functions"] or [],
        model=model_file["model"],
        parameters=model_file["parameters"],
        mappings=raw["mappings"] or {},
    )
