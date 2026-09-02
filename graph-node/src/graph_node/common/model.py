"""The shape of a graph a loader intends to write.

Shared by the data and knowledge loaders. These lived in `data/build.py` until
the knowledge loader needed them too - importing them from `data` would have
made knowledge depend on data for no reason other than where the code happened
to be first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class Edge:
    type: str
    start: str
    end: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.start, self.type, self.end)


@dataclass
class IntendedGraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    #: Kinetic chains. Populated by the data builder only; the knowledge
    #: builder leaves it empty.
    chains: list[Any] = field(default_factory=list)
    #: Non-fatal, but a human should see them.
    warnings: list[str] = field(default_factory=list)
    #: Fatal. The rebuild must not be written while any of these stand.
    errors: list[str] = field(default_factory=list)

    def nodes_by_label(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.nodes:
            counts[node.label] = counts.get(node.label, 0) + 1
        return counts

    def edges_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in self.edges:
            counts[edge.type] = counts.get(edge.type, 0) + 1
        return counts
