"""Mark and sweep: how a rebuild removes what no longer exists upstream.

The problem this solves
-----------------------
Rebuilding with MERGE adds and updates, but never deletes. If an experiment is
renamed or removed from the share drive, its nodes stay in the graph forever,
and nothing reports it. The graph slowly fills with things that are not true.

The mechanism
-------------
Think of it as a stocktake. Every rebuild gets an id - a timestamp. As the
loader writes each node and relationship, it stamps it with that id. When the
run finishes, one query deletes everything in scope that is *not* carrying the
current stamp.

A node only keeps an old stamp if this run did not write it, which means its
source data is gone. So the sweep removes exactly the orphans and nothing else.
You never have to work out what to delete; you enumerate what still exists and
deletion falls out of the difference.

Why not wipe and reload
-----------------------
Deleting everything first and rewriting is simpler, but the graph is empty for
the duration, and a crash halfway leaves it that way. With mark and sweep a
crash simply means the sweep never runs: no deletions, nothing lost, and the
next rebuild puts it right.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neo4j import Session

from .ownership import GraphScope

logger = logging.getLogger(__name__)

#: Property carrying the stamp. Leading underscore marks it as bookkeeping
#: rather than science, so it is easy to exclude from anything user-facing.
RUN_PROPERTY = "_run"

#: Refuse to sweep away more than this fraction of a scope in one run. A
#: rebuild that suddenly matches almost nothing is far more likely to be a
#: broken source path than a genuine mass deletion, and the sweep is the one
#: irreversible step in the pipeline. Override deliberately with
#: `sweep(..., allow_mass_deletion=True)`.
MASS_DELETION_THRESHOLD = 0.20


#: Refuse the rebuild if more than this fraction of discovered sources cannot
#: be read. Sibling of MASS_DELETION_THRESHOLD, and learned the same way.
#:
#: A single unreadable file is a warning: the file really is corrupt and its
#: experiment really should leave the graph. Hundreds at once is not that - it
#: is credentials, a network, a permission. The distinction matters because an
#: unreadable source produces no nodes, and no nodes is indistinguishable from
#: deleted data by the time the sweep runs.
#:
#: Observed 2026-09-08: pointed at S3 with a write-only key, all 299 sources
#: failed GetObject and the plan offered to delete all 2,179 nodes. The sweep
#: threshold would have caught it, but the dry run had already reported a plan
#: worth applying. One guard behind another is not the same as one guard.
UNREADABLE_SOURCE_THRESHOLD = 0.20


def systemic_read_failure(unreadable: int, discovered: int) -> str | None:
    """Why the rebuild should refuse, or None if the failures look isolated."""
    if not discovered or not unreadable:
        return None
    share = unreadable / discovered
    if share <= UNREADABLE_SOURCE_THRESHOLD:
        return None
    return (
        f"{unreadable} of {discovered} source files could not be read "
        f"({share:.0%}). That is not a few bad files, it is the source itself - "
        "credentials, a permission, or the wrong location. Refusing to build a "
        "graph from what did read, because every experiment that failed would "
        "be swept as though its data had been deleted."
    )


def new_run_id() -> str:
    """A stamp for one rebuild. Sorts chronologically and reads as a date."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class SweepResult:
    nodes_deleted: int
    relationships_deleted: int
    nodes_kept: int
    aborted: bool = False
    reason: str | None = None


def sweep(
    session: Session,
    scope: GraphScope,
    run_id: str,
    *,
    dry_run: bool = False,
    allow_mass_deletion: bool = False,
) -> SweepResult:
    """Delete everything in `scope` not stamped with `run_id`.

    Two passes, because they catch different things. The relationship pass
    removes edges whose endpoints both survive but which should no longer
    exist - a NEXT_EXP edge orphaned by a shifted chain boundary is the case
    that matters here. The node pass then removes the nodes themselves.

    Node deletion is DETACH DELETE: a node cannot leave its relationships
    behind, since Neo4j has no dangling edges. That does mean a relationship
    owned by another scope is removed if it points at a node this scope
    deletes, which is correct - the alternative is not representable.
    """
    labels = sorted(scope.labels)
    rel_types = sorted(scope.relationship_types)

    stale_nodes = session.run(
        """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN $labels)
          AND (n[$prop] IS NULL OR n[$prop] <> $run_id)
        RETURN count(n) AS c
        """,
        labels=labels,
        prop=RUN_PROPERTY,
        run_id=run_id,
    ).single()["c"]

    current_nodes = session.run(
        """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN $labels)
          AND n[$prop] = $run_id
        RETURN count(n) AS c
        """,
        labels=labels,
        prop=RUN_PROPERTY,
        run_id=run_id,
    ).single()["c"]

    total = stale_nodes + current_nodes
    if total and not allow_mass_deletion:
        share = stale_nodes / total
        if share > MASS_DELETION_THRESHOLD:
            reason = (
                f"sweep would delete {stale_nodes}/{total} nodes "
                f"({share:.0%}) in scope {scope.name!r}, above the "
                f"{MASS_DELETION_THRESHOLD:.0%} threshold. This usually means "
                "the rebuild read the wrong source directory rather than that "
                "the data really vanished. Re-run with allow_mass_deletion=True "
                "if the deletion is intended."
            )
            logger.error(reason)
            return SweepResult(0, 0, current_nodes, aborted=True, reason=reason)

    if dry_run:
        return SweepResult(stale_nodes, 0, current_nodes)

    # Deletion counts come from the driver's own counters rather than a RETURN:
    # an entity cannot be returned after it has been deleted in the same query.
    rels_deleted = 0
    if rel_types:
        summary = session.run(
            """
            MATCH ()-[r]->()
            WHERE type(r) IN $types
              AND (r[$prop] IS NULL OR r[$prop] <> $run_id)
            DELETE r
            """,
            types=rel_types,
            prop=RUN_PROPERTY,
            run_id=run_id,
        ).consume()
        rels_deleted = summary.counters.relationships_deleted

    summary = session.run(
        """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN $labels)
          AND (n[$prop] IS NULL OR n[$prop] <> $run_id)
        DETACH DELETE n
        """,
        labels=labels,
        prop=RUN_PROPERTY,
        run_id=run_id,
    ).consume()
    nodes_deleted = summary.counters.nodes_deleted
    rels_deleted += summary.counters.relationships_deleted

    logger.info(
        "sweep(%s): deleted %d nodes, %d relationships; %d nodes current",
        scope.name,
        nodes_deleted,
        rels_deleted,
        current_nodes,
    )
    return SweepResult(nodes_deleted, rels_deleted, current_nodes)
