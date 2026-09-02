"""Building the knowledge graph, and attaching it to the data graph.

Two halves:

**The vocabulary.** Concepts, species, functions, the kinetic model and its
parameters, all read from YAML, plus the edges between them.

**The attachment.** `INSTANCE_OF` and `FIT_BY` edges that connect data nodes to
concepts - "this pretreatment step *is an* evacuation". These are what make the
knowledge graph useful rather than a glossary sitting off to one side.

The attachment rules come from `original/knowledge_graph_instructions.txt` §7,
declared in `knowledge/mappings.yaml`. The `when:` clauses there are
documentation; the logic is here, ported from `load_knowledge.py`.

**`DELTA_FROM` and `RELATIVE_TO` are deliberately absent.** The original emitted
them from this loader, but they are arithmetic on AdsParams with no knowledge
input, so they belong to the data graph and live in `data/drift.py`. Emitting
them from both would have two loaders writing the same edges with different run
stamps, and whichever swept last would delete the other's.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..common import ids
from ..common.model import Edge, IntendedGraph, Node
from .source import KnowledgeSource

EVACUATION_GASES = frozenset({"RoughPump", "TurboPump"})
CO_ISOTOPES = frozenset({"CO", "13CO", "12CO"})


def _build_vocabulary(source: KnowledgeSource) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []

    for concept in source.concepts:
        name = concept["name"]
        properties = {
            "name": name,
            "kind": concept.get("kind"),
            "definition": concept.get("definition"),
        }
        # Only carried when present. Two of fifteen concepts have aliases, and
        # writing an empty list would make "no aliases" and "aliases not
        # recorded" indistinguishable.
        if concept.get("aliases"):
            properties["aliases"] = list(concept["aliases"])
        nodes.append(Node(ids.concept_id(name), "ChemConcept", properties))

        parent = concept.get("subtype_of")
        if parent:
            edges.append(
                Edge("SUBTYPE_OF", ids.concept_id(name), ids.concept_id(parent))
            )

    for species in source.species:
        formula = species["formula"]
        nodes.append(
            Node(
                ids.species_id(formula),
                "ChemSpecies",
                {"formula": formula, "role": list(species.get("role") or [])},
            )
        )

    for function in source.py_functions:
        name = function["name"]
        nodes.append(
            Node(
                ids.py_function_id(name),
                "PyFunction",
                {
                    "name": name,
                    "signature": function.get("signature"),
                    "docstring": function.get("docstring"),
                    # Kept as a JSON string on purpose: the parameter list is
                    # a list of maps, and Neo4j properties cannot nest.
                    "parameters_json": _json_dumps(function.get("parameters") or []),
                },
            )
        )

    model_name = source.model_name
    nodes.append(
        Node(
            ids.kinetic_model_id(model_name),
            "KineticModel",
            {
                "name": model_name,
                "description": source.model.get("description"),
                "equations": list(source.model.get("equations") or []),
            },
        )
    )

    for parameter in source.parameters:
        name = parameter["name"]
        parameter_id = ids.model_parameter_id(model_name, name)
        nodes.append(
            Node(
                parameter_id,
                "ModelParameter",
                {
                    "id": parameter_id,
                    "name": name,
                    "model_name": model_name,
                    "param_role": parameter.get("role"),
                    "quantity_kind": parameter.get("quantity_kind"),
                    "units": parameter.get("units"),
                    "definition": parameter.get("definition"),
                    "fitted": parameter.get("fitted"),
                },
            )
        )
        edges.append(
            Edge("PARAMETER_OF", parameter_id, ids.kinetic_model_id(model_name))
        )

    mappings = source.mappings
    for function_name, concepts in (mappings.get("py_to_concept") or {}).items():
        for concept in concepts:
            edges.append(
                Edge(
                    "IMPLEMENTS",
                    ids.py_function_id(function_name),
                    ids.concept_id(concept),
                )
            )

    for concept, formulas in (mappings.get("concept_to_species") or {}).items():
        for formula in formulas:
            edges.append(
                Edge("USES_SPECIES", ids.concept_id(concept), ids.species_id(formula))
            )

    return nodes, edges


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _attach_to_data(
    source: KnowledgeSource, data: IntendedGraph
) -> tuple[list[Edge], dict[str, int], list[str]]:
    """INSTANCE_OF and FIT_BY, per §7 rules. Returns (edges, fire counts, warnings).

    Every matching rule fires; there is no short-circuiting. A pretreatment
    that ramps *and* dose oxygen is both a thermal_ramp and an oxidation.
    """
    rules = (source.mappings or {}).get("instance_of_rules") or {}
    species_to_chemistry = {
        key: (value if isinstance(value, list) else [value])
        for key, value in (rules.get("species_to_chemistry") or {}).items()
    }

    edges: list[Edge] = []
    fired: Counter[str] = Counter()

    def emit(start: str, concept: str, rule: str) -> None:
        edges.append(Edge("INSTANCE_OF", start, ids.concept_id(concept)))
        fired[rule] += 1

    by_id = {node.id: node for node in data.nodes}

    # Which Filename each ExpConditions and AdsParams belongs to, so the rules
    # that depend on the parent experiment can find it.
    conditions_to_filename: dict[str, str] = {}
    adsparams_to_filename: dict[str, str] = {}
    for edge in data.edges:
        if edge.type == "CONDUCTED_UNDER":
            conditions_to_filename[edge.end] = edge.start
        elif edge.type == "YIELDS":
            filename = conditions_to_filename.get(edge.start)
            if filename:
                adsparams_to_filename[edge.end] = filename

    for node in data.nodes:
        properties = node.properties

        if node.label == "Pretreatment":
            gases = properties.get("gas") or []
            rate = properties.get("rate")
            duration = properties.get("duration")

            if any(gas in EVACUATION_GASES for gas in gases):
                emit(node.id, "evacuation", "R1_evacuation")
            for gas in gases:
                for concept in species_to_chemistry.get(gas, []):
                    emit(node.id, concept, "R2_chemistry")
            if rate is not None and rate > 0:
                emit(node.id, "thermal_ramp", "R3_ramp")
            if rate == 0 and duration is not None and duration > 0:
                emit(node.id, "thermal_soak", "R4_soak")

        elif node.label == "ExpConditions":
            filename_id = conditions_to_filename.get(node.id)
            if filename_id is None:
                continue
            exp_type = by_id[filename_id].properties.get("exp_type")
            has_co = any(gas in CO_ISOTOPES for gas in properties.get("gas") or [])
            if has_co and exp_type == "adsorption":
                emit(node.id, "adsorption_measurement", "E1_adsorption")
            if has_co and exp_type == "isotopic_exchange":
                emit(node.id, "isotopic_exchange_measurement", "E2_isotopic")

        elif node.label == "Filename":
            if properties.get("is_reference") is True:
                emit(node.id, "reference_state", "F1_reference")

        elif node.label == "AdsParams":
            filename_id = adsparams_to_filename.get(node.id)
            if filename_id and by_id[filename_id].properties.get("is_reference") is True:
                emit(node.id, "reference_state", "A1_reference")
            # A2, always: every AdsParams was produced by fitting the model.
            edges.append(
                Edge("FIT_BY", node.id, ids.kinetic_model_id(source.model_name))
            )
            fired["A2_fit_by"] += 1

    # A rule that never fires is either dead or broken, and the difference
    # matters. E2 legitimately never fires while isotopic runs are excluded.
    warnings = [
        f"rule {rule} matched nothing"
        for rule in (
            "R1_evacuation", "R2_chemistry", "R3_ramp", "R4_soak",
            "E1_adsorption", "F1_reference", "A1_reference", "A2_fit_by",
        )
        if not fired[rule]
    ]
    return edges, dict(fired), warnings


def build(source: KnowledgeSource, data: IntendedGraph) -> IntendedGraph:
    """The knowledge graph, including its attachment to `data`.

    `data` is the intended data graph, not the stored one, so both halves of a
    rebuild are computed from the same sources in one pass. Attaching to the
    database instead would leave the overlay describing whatever the previous
    rebuild happened to write.
    """
    graph = IntendedGraph()
    nodes, edges = _build_vocabulary(source)
    graph.nodes.extend(nodes)
    graph.edges.extend(edges)

    attachment, fired, warnings = _attach_to_data(source, data)
    graph.edges.extend(attachment)
    graph.warnings.extend(warnings)

    missing = [
        edge
        for edge in edges
        if edge.type in ("SUBTYPE_OF", "IMPLEMENTS", "USES_SPECIES")
        and edge.end not in {n.id for n in nodes}
    ]
    for edge in missing:
        # A mapping naming a concept or species that no YAML defines. The edge
        # would silently match nothing at write time.
        graph.errors.append(
            f"{edge.type} points at {edge.end}, which no YAML file defines"
        )

    graph.rule_fire_counts = fired  # type: ignore[attr-defined]
    return graph
