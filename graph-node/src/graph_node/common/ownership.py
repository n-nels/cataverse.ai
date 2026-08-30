"""Which loader owns which part of the graph.

The data graph and the knowledge graph share one Neo4j instance, and the plan
is for the knowledge side to grow a lot (literature ingestion, and later a
context graph that intersects both). A boundary that exists only as an
intention will not survive that, so it is written down here and enforced by a
test rather than by remembering.

This is not bureaucracy: it is what makes the sweep safe. `sweep()` deletes
anything a rebuild did not touch, and it must be told exactly how far its
authority extends. Without a scope, a data rebuild would happily delete every
ChemConcept in the graph because it did not write any.

The concrete failure this is designed to catch already happened once:
DELTA_FROM is arithmetic on AdsParams and belongs to the data graph, but it
shipped in knowledge.cypher because that is where it got written.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphScope:
    """The labels and relationship types one loader is allowed to write."""

    name: str
    labels: frozenset[str]
    relationship_types: frozenset[str]

    def owns_label(self, label: str) -> bool:
        return label in self.labels

    def owns_relationship(self, rel_type: str) -> bool:
        return rel_type in self.relationship_types


#: Everything measured, plus everything derived from measurements.
#:
#: DELTA_FROM and RELATIVE_TO are here rather than in KNOWLEDGE because they are
#: pure arithmetic over AdsParams properties (delta_ka = source.pfo_sec_k_a -
#: target.pfo_sec_k_a, and the same for q_e / k_s / k_p / q_inf / q0 / time_s).
#: No knowledge-graph input participates. The dividing line is provenance, not
#: node type.
DATA = GraphScope(
    name="data",
    labels=frozenset(
        {
            "Material",
            "Filename",
            "Pretreatment",
            "ExpConditions",
            "AdsParams",
            "KineticChain",
        }
    ),
    relationship_types=frozenset(
        {
            "HAS_EXPERIMENT",
            "CONDUCTED_UNDER",
            "HAS_STEP",
            "NEXT_STEP",
            "YIELDS",
            "IN_CHAIN",
            "NEXT_EXP",
            "DELTA_FROM",
            "RELATIVE_TO",
        }
    ),
)

#: Hand-authored chemistry: concepts, species, the Python functions that
#: implement them, and the kinetic models being fitted. Sourced from YAML today,
#: literature later.
KNOWLEDGE = GraphScope(
    name="knowledge",
    labels=frozenset(
        {
            "ChemConcept",
            "ChemSpecies",
            "PyFunction",
            "ModelParameter",
            "KineticModel",
        }
    ),
    relationship_types=frozenset(),  # populated when the knowledge loader lands
)

ALL_SCOPES = (DATA, KNOWLEDGE)


def check_disjoint() -> None:
    """Raise if two scopes claim the same label or relationship type.

    Overlap would make the sweep ambiguous: whichever loader ran last would
    delete the other's work.
    """
    for i, a in enumerate(ALL_SCOPES):
        for b in ALL_SCOPES[i + 1 :]:
            shared_labels = a.labels & b.labels
            shared_rels = a.relationship_types & b.relationship_types
            if shared_labels or shared_rels:
                raise ValueError(
                    f"Scopes {a.name!r} and {b.name!r} overlap - "
                    f"labels={sorted(shared_labels)} "
                    f"relationships={sorted(shared_rels)}"
                )
