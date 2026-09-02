"""Writing the intended graph into Neo4j.

Generic over nodes and edges, so the knowledge loader can reuse it.

Two decisions worth knowing about:

**`SET n = props`, not `SET n += props`.** `+=` merges, leaving behind any
property the stored node has that the source no longer produces. That is not a
rebuild, it is an accumulation - and it would silently keep `pressure_meas_g1`
alongside the new `pressure_meas_mfld` forever. Replacing outright means the
node ends up exactly as the source describes it, which is the whole point.

**Constraints are created before anything is written.** They are the original
pipeline's `constraints.cypher`, which was specified and never built. They stop
duplicates, and their backing indexes are what keep ~1,900 MERGEs from turning
into ~1,900 full label scans.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Iterable, Sequence

from neo4j import Session

from . import ids
from .rebuild import RUN_PROPERTY

logger = logging.getLogger(__name__)

#: Rows per transaction. Aura's free tier is memory-limited, and one enormous
#: transaction is the easiest way to hit that. Smaller batches also mean a
#: failure part-way leaves less to redo - and leaves the sweep unrun, so
#: nothing is deleted on the strength of a partial write.
BATCH_SIZE = 500


def _batched(rows: Sequence[dict], size: int = BATCH_SIZE):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def ensure_constraints(session: Session) -> list[str]:
    """Create a uniqueness constraint on each label's identity property.

    Idempotent - IF NOT EXISTS - so this is safe to run before every rebuild.
    Returns the constraints it asked for, for logging.
    """
    created: list[str] = []
    for label, (prop, _) in sorted(ids.IDENTITY.items()):
        name = f"{label.lower()}_{prop}_unique"
        session.run(
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.`{prop}` IS UNIQUE"
        ).consume()
        created.append(f"{label}.{prop}")
    return created


def _identity_value(label: str, node_id: str) -> str:
    """The stored key for a node, recovered from its synthetic id."""
    _, prefix = ids.IDENTITY[label]
    return node_id.removeprefix(prefix) if prefix else node_id


def write_nodes(session: Session, nodes: Iterable, run_id: str) -> int:
    """MERGE every node on its identity property and stamp it with `run_id`."""
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        prop, _ = ids.IDENTITY[node.label]
        key = _identity_value(node.label, node.id)
        # The identity property has to be in the payload: `SET n = props` would
        # otherwise strip the very key the node was matched on.
        by_label[node.label].append(
            {"key": key, "props": {**node.properties, prop: key}}
        )

    written = 0
    for label, rows in sorted(by_label.items()):
        prop, _ = ids.IDENTITY[label]
        # Label and property names cannot be Cypher parameters. Both come from
        # the IDENTITY constant, so nothing external reaches the query text.
        query = (
            f"UNWIND $rows AS row "
            f"MERGE (n:{label} {{`{prop}`: row.key}}) "
            f"SET n = row.props "
            f"SET n.`{RUN_PROPERTY}` = $run_id"
        )
        for batch in _batched(rows):
            session.run(query, rows=batch, run_id=run_id).consume()
            written += len(batch)
        logger.info("wrote %d %s node(s)", len(rows), label)

    return written


def write_relationships(
    session: Session, edges: Iterable, node_labels: dict[str, str], run_id: str
) -> int:
    """MERGE every edge and stamp it. `node_labels` maps node id to its label.

    Grouped by (type, start label, end label) because none of the three can be
    a parameter. In practice that is about nine groups - each relationship type
    connects one pair of labels.
    """
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for edge in edges:
        start_label = node_labels.get(edge.start)
        end_label = node_labels.get(edge.end)
        if start_label is None or end_label is None:
            # An edge to a node that was never built. Should not happen; if it
            # does, dropping it is right - the alternative is a MATCH that finds
            # nothing and silently writes nothing anyway.
            skipped += 1
            continue
        grouped[(edge.type, start_label, end_label)].append(
            {
                "start": _identity_value(start_label, edge.start),
                "end": _identity_value(end_label, edge.end),
                "props": dict(edge.properties),
            }
        )

    if skipped:
        logger.warning("skipped %d edge(s) with an unknown endpoint", skipped)

    written = 0
    for (rel_type, start_label, end_label), rows in sorted(grouped.items()):
        start_prop, _ = ids.IDENTITY[start_label]
        end_prop, _ = ids.IDENTITY[end_label]
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{start_label} {{`{start_prop}`: row.start}}) "
            f"MATCH (b:{end_label} {{`{end_prop}`: row.end}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r = row.props "
            f"SET r.`{RUN_PROPERTY}` = $run_id"
        )
        for batch in _batched(rows):
            session.run(query, rows=batch, run_id=run_id).consume()
            written += len(batch)
        logger.info(
            "wrote %d %s edge(s) (%s -> %s)",
            len(rows),
            rel_type,
            start_label,
            end_label,
        )

    return written
