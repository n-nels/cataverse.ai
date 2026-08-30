"""Comparing the intended graph against the stored one.

This is the dry run. It answers "what would a rebuild change?" without changing
anything, which matters because the alternative is finding out by doing it to
the live database.

Reads only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from neo4j import Session

from ..common.ownership import DATA
from .build import IntendedGraph


@dataclass
class Plan:
    nodes_to_create: dict[str, int] = field(default_factory=dict)
    nodes_to_update: dict[str, int] = field(default_factory=dict)
    nodes_to_delete: dict[str, int] = field(default_factory=dict)
    relationships_intended: int = 0
    relationships_stored: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_safe_to_apply(self) -> bool:
        return not self.errors

    @property
    def total_deletions(self) -> int:
        return sum(self.nodes_to_delete.values())


def _stored_ids_by_label(session: Session) -> dict[str, set[str]]:
    """Every stored data node's id, grouped by label.

    Filename has no `id` property - it is keyed on `base_name` - so it is read
    separately and given the same synthetic form the builder produces.
    """
    stored: dict[str, set[str]] = {label: set() for label in DATA.labels}

    for record in session.run(
        """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN $labels) AND n.id IS NOT NULL
        RETURN labels(n)[0] AS label, collect(n.id) AS ids
        """,
        labels=sorted(DATA.labels),
    ):
        stored[record["label"]] = set(record["ids"])

    filenames = session.run(
        "MATCH (f:Filename) RETURN collect(f.base_name) AS names"
    ).single()["names"]
    stored["Filename"] = {f"fn_{name}" for name in filenames}

    return stored


def plan(session: Session, intended: IntendedGraph) -> Plan:
    """Diff `intended` against the database. Makes no writes."""
    result = Plan(
        warnings=list(intended.warnings),
        errors=list(intended.errors),
        relationships_intended=len(intended.edges),
    )

    stored = _stored_ids_by_label(session)
    intended_by_label: dict[str, set[str]] = {label: set() for label in DATA.labels}
    for node in intended.nodes:
        intended_by_label.setdefault(node.label, set()).add(node.id)

    for label in sorted(DATA.labels):
        want = intended_by_label.get(label, set())
        have = stored.get(label, set())
        if created := len(want - have):
            result.nodes_to_create[label] = created
        if updated := len(want & have):
            result.nodes_to_update[label] = updated
        if deleted := len(have - want):
            result.nodes_to_delete[label] = deleted

    result.relationships_stored = session.run(
        "MATCH ()-[r]->() WHERE type(r) IN $types RETURN count(r) AS c",
        types=sorted(DATA.relationship_types),
    ).single()["c"]

    return result


def render(plan_result: Plan, intended: IntendedGraph) -> str:
    """A human-readable dry-run report."""
    lines: list[str] = []
    add = lines.append

    add("Rebuild plan (dry run - nothing was written)")
    add("=" * 60)

    add("")
    add(f"{'label':<16}{'create':>8}{'update':>8}{'delete':>8}")
    add("-" * 40)
    for label in sorted(DATA.labels):
        create = plan_result.nodes_to_create.get(label, 0)
        update = plan_result.nodes_to_update.get(label, 0)
        delete = plan_result.nodes_to_delete.get(label, 0)
        if create or update or delete:
            add(f"{label:<16}{create:>8}{update:>8}{delete:>8}")

    add("")
    add(f"relationships intended : {plan_result.relationships_intended}")
    add(f"relationships stored   : {plan_result.relationships_stored}")
    for rel_type, count in sorted(intended.edges_by_type().items()):
        add(f"    {rel_type:<18} {count}")

    add("")
    add(f"kinetic chains: {len(intended.chains)}")
    for chain in intended.chains:
        add(
            f"    {chain.node_id}  {chain.started_at}  "
            f"{len(chain.base_names)} experiments  mass_g={chain.mass_g}"
        )

    if plan_result.warnings:
        add("")
        add(f"warnings ({len(plan_result.warnings)}):")
        for warning in plan_result.warnings:
            add(f"    {warning}")

    if plan_result.errors:
        add("")
        add(f"ERRORS ({len(plan_result.errors)}) - rebuild would be refused:")
        for error in plan_result.errors:
            add(f"    {error}")

    add("")
    if not plan_result.is_safe_to_apply:
        add("Result: BLOCKED. Fix the errors above before applying.")
    elif plan_result.total_deletions:
        add(
            f"Result: would apply, deleting {plan_result.total_deletions} node(s). "
            "Check the delete column is what you expect."
        )
    else:
        add("Result: would apply cleanly, no deletions.")

    return "\n".join(lines)


def summarise_missing_adsparams(intended: IntendedGraph) -> dict[str, Any]:
    """AdsParams is not built yet; report that plainly rather than silently."""
    return {
        "adsparams_built": any(n.label == "AdsParams" for n in intended.nodes),
        "note": (
            "AdsParams and YIELDS are absent: the fit CSV reader is not written "
            "yet, pending a sample *_CarbonylPeakArea.csv. A rebuild run now "
            "would sweep away the 238 AdsParams nodes currently stored."
        ),
    }
