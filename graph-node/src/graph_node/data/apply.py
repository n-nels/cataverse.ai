"""Applying a rebuild: write everything, then sweep what is left over.

The order matters and is the whole safety argument. Nodes and relationships are
written and stamped first; only then does the sweep delete anything not
carrying the current stamp. If the write fails half way, the sweep never runs -
so a partial write leaves the graph stale but intact, and the next rebuild
fixes it. There is no window in which the graph is empty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from neo4j import Session

from ..common.model import IntendedGraph
from ..common.ownership import DATA, GraphScope
from ..common.rebuild import SweepResult, new_run_id, sweep
from ..common.writer import ensure_constraints, write_nodes, write_relationships

logger = logging.getLogger(__name__)


class RefusedError(Exception):
    """The rebuild was not attempted because the plan was not safe."""


@dataclass
class ApplyResult:
    run_id: str
    nodes_written: int = 0
    relationships_written: int = 0
    sweep: SweepResult | None = None
    constraints: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"run id                 : {self.run_id}",
            f"nodes written          : {self.nodes_written}",
            f"relationships written  : {self.relationships_written}",
        ]
        if self.sweep is None:
            lines.append("sweep                  : not run")
        elif self.sweep.aborted:
            lines.append(f"sweep                  : ABORTED - {self.sweep.reason}")
        else:
            lines.append(
                f"sweep                  : deleted {self.sweep.nodes_deleted} node(s), "
                f"{self.sweep.relationships_deleted} relationship(s)"
            )
        return "\n".join(lines)


def apply(
    session: Session,
    intended: IntendedGraph,
    scope: GraphScope = DATA,
    *,
    allow_mass_deletion: bool = False,
    run_id: str | None = None,
    extra_node_labels: dict[str, str] | None = None,
) -> ApplyResult:
    """Write `intended` into the database and sweep the remainder.

    Refuses outright if the build reported errors. Those are conditions like a
    null `is_new` or a mass disagreement within a chain - cases where the source
    data does not determine what the graph should be. Writing anyway would put
    a guess into the database.
    """
    if intended.errors:
        raise RefusedError(
            f"{len(intended.errors)} error(s) in the source data; "
            "nothing was written. First: " + intended.errors[0]
        )

    result = ApplyResult(run_id=run_id or new_run_id())
    result.constraints = ensure_constraints(session)

    # Knowledge edges (INSTANCE_OF, FIT_BY) start on *data* nodes, which are
    # not in this graph's node list. Without their labels the writer cannot
    # build the MATCH and would drop them as unknown endpoints.
    node_labels = dict(extra_node_labels or {})
    node_labels.update({node.id: node.label for node in intended.nodes})
    result.nodes_written = write_nodes(session, intended.nodes, result.run_id)
    result.relationships_written = write_relationships(
        session, intended.edges, node_labels, result.run_id
    )

    result.sweep = sweep(
        session,
        scope,
        result.run_id,
        allow_mass_deletion=allow_mass_deletion,
    )
    return result
