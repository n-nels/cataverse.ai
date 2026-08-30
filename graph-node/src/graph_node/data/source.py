"""Reading experiment metadata off the share drive.

One `<base>_expParams.json` per experiment, written by
`orchestration/src/experiments/session.py`. That writer is the schema of record
- not the vendored instructions in `original/`, whose field names are stale by
their own admission.

Verified against two real files spanning the dataset (2025-02 and 2026-08): the
shape is stable, and both use `pressure_meas_mfld` / `pressure_meas_cell`. The
older `pressure_meas_g1` / `g2` spelling exists only in the *database*, never in
the source, so there is no dual-spelling problem to handle here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

#: Suffix identifying an experiment metadata file.
SUFFIX = "_expParams.json"

REQUIRED_TOP_LEVEL = ("base_name", "datetime", "material", "filename_flags")

#: Material fields that make up the node id, and so must never be retyped.
#:
#: `material_id` turns `.` into `p`, so coercing `support_sa` from 54 to 54.0
#: rewrites the id from `mat_pd_0p0339_ceo2_54` to `..._54p0` - a different
#: node. Every Material in the database would be orphaned, and the sweep would
#: then delete the originals. Normalisation stops at this boundary.
MATERIAL_IDENTITY_FIELDS = frozenset({"metal", "metal_loading", "support", "support_sa"})


class SourceError(Exception):
    """A source file could not be read as an experiment."""


def _as_float(value: Any) -> Any:
    """Coerce numbers to float, leaving everything else alone.

    Neo4j types each property value individually, so the same property can end
    up INTEGER on one node and FLOAT on another - which then breaks queries that
    compare or aggregate across them. This is not hypothetical: the observed
    files disagree already, with `temp: 600` and `rate: 20` in the 2025 file
    against `temp: 450.0` and `rate: 20.0` in the 2026 one.

    Booleans are excluded deliberately - `bool` is a subclass of `int` in
    Python, and `chiller: false` must stay a boolean.

    Lists are mapped element-wise. `pressure_calc` is list-valued and the same
    disagreement shows up inside it: the database holds `[0]` on some nodes and
    the source files hold `[0.8207]`, which Neo4j stores as INTEGER[] and
    FLOAT[] respectively.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [_as_float(v) for v in value]
    return value


def _clean_block(block: dict[str, Any], *, preserve: frozenset[str] = frozenset()) -> dict[str, Any]:
    return {
        k: v if k in preserve else _as_float(v)
        for k, v in block.items()
    }


@dataclass(frozen=True)
class Experiment:
    """One experiment's metadata, normalised and ready to become nodes."""

    base_name: str
    started_at: datetime
    material: dict[str, Any]
    flags: dict[str, Any]
    pretreatments: list[dict[str, Any]]
    conditions: dict[str, Any]
    source_path: Path
    #: Problems worth a human's attention that are not fatal. Collected rather
    #: than raised so one bad file cannot stop a whole rebuild.
    warnings: list[str] = field(default_factory=list)

    @property
    def is_new_sample(self) -> bool | None:
        return self.flags.get("is_new")

    @property
    def has_csv(self) -> bool:
        return bool(self.flags.get("has_csv"))

    @property
    def mass_g(self) -> float | None:
        """Catalyst mass. Lives on KineticChain, not Material.

        It is a property of the physical loading rather than of the material
        formulation, and is constant within a chain.
        """
        return self.material.get("mass_g")


def load(path: str | Path) -> Experiment:
    """Parse one `_expParams.json`. Raises SourceError if it is unusable."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceError(f"{path.name}: {exc}") from exc

    missing = [k for k in REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        raise SourceError(f"{path.name}: missing key(s) {', '.join(missing)}")

    try:
        started_at = datetime.fromisoformat(raw["datetime"])
    except (TypeError, ValueError) as exc:
        raise SourceError(f"{path.name}: unparseable datetime {raw['datetime']!r}") from exc

    warnings: list[str] = []

    steps: list[dict[str, Any]] = []
    for position, step in enumerate(raw.get("pretreatments") or [], start=1):
        if step.get("step_index") is None:
            # This is the hollow-node bug, caught at the source rather than
            # written into the graph. pre_20250802_073857_pd_ceo2_003-001_1
            # exists in the database with an id and no other properties at all,
            # because a step like this was loaded without complaint.
            warnings.append(
                f"pretreatment at position {position} has no step_index; skipped"
            )
            continue
        steps.append(_clean_block(step))

    conditions = raw.get("exp_conditions") or {}
    if not conditions and raw["filename_flags"].get("exp_success"):
        # Absent conditions are normal for a run that was started and abandoned,
        # but a *successful* run without them means something was lost.
        warnings.append("exp_success is true but exp_conditions is empty")

    return Experiment(
        base_name=raw["base_name"],
        started_at=started_at,
        material=_clean_block(raw["material"], preserve=MATERIAL_IDENTITY_FIELDS),
        flags=dict(raw["filename_flags"]),
        pretreatments=steps,
        conditions=_clean_block(conditions),
        source_path=path,
        warnings=warnings,
    )


def discover(root: str | Path) -> list[Path]:
    """Every experiment metadata file beneath `root`, sorted by name.

    Sorted so a rebuild is reproducible: the same tree always yields the same
    order, which matters because chain construction is order-dependent.
    """
    return sorted(Path(root).rglob(f"*{SUFFIX}"))
