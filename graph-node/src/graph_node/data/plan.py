"""Comparing the intended graph against the stored one.

This is the dry run. It answers "what would a rebuild change?" without changing
anything, which matters because the alternative is finding out by doing it to
the live database.

Reads only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from neo4j import Session

from ..common import ids
from ..common.model import IntendedGraph
from ..common.ownership import DATA, GraphScope


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


def _stored_ids_by_label(session: Session, scope: GraphScope) -> dict[str, set[str]]:
    """Every stored data node, as the synthetic id the builder would give it.

    Each label is read on its own identity property. Filename is keyed on
    `base_name` and KineticChain on `chain_id` - neither has an `id` property.
    Reading them all as `n.id` returns nothing for those two, which makes the
    plan report 249 filenames and 6 chains as new and their originals as
    deletions.
    """
    stored: dict[str, set[str]] = {}

    for label in sorted(scope.labels):
        prop, _ = ids.IDENTITY[label]
        # Label and property are interpolated rather than parameterised because
        # Cypher allows neither as a parameter. Both come from IDENTITY, which
        # is a module constant, so nothing user-supplied reaches the query.
        record = session.run(
            f"MATCH (n:{label}) WHERE n.`{prop}` IS NOT NULL "
            f"RETURN collect(n.`{prop}`) AS values"
        ).single()
        stored[label] = {
            ids.node_id_from_stored(label, value) for value in record["values"]
        }

    return stored


def plan(
    session: Session, intended: IntendedGraph, scope: GraphScope = DATA
) -> Plan:
    """Diff `intended` against the database. Makes no writes."""
    result = Plan(
        warnings=list(intended.warnings),
        errors=list(intended.errors),
        relationships_intended=len(intended.edges),
    )

    stored = _stored_ids_by_label(session, scope)
    intended_by_label: dict[str, set[str]] = {label: set() for label in scope.labels}
    for node in intended.nodes:
        intended_by_label.setdefault(node.label, set()).add(node.id)

    for label in sorted(scope.labels):
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
        types=sorted(scope.relationship_types),
    ).single()["c"]

    return result


def render(
    plan_result: Plan, intended: IntendedGraph, scope: GraphScope = DATA
) -> str:
    """A human-readable dry-run report."""
    lines: list[str] = []
    add = lines.append

    add(f"Rebuild plan: {scope.name} graph (dry run - nothing was written)")
    add("=" * 60)

    add("")
    add(f"{'label':<16}{'create':>8}{'update':>8}{'delete':>8}")
    add("-" * 40)
    for label in sorted(scope.labels):
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

    if intended.chains:
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
