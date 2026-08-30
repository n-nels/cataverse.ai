"""Turning parsed experiments into the graph they imply.

Pure functions: nothing here touches the database. That is what makes the dry
run possible - the intended graph is computed in full, then compared against
what is actually stored.

Ported from `original/scripts/load_graph.py`, with one behavioural change. The
original calls `sys.exit()` on a null `is_new` or a mass mismatch, which is
right for a script a human runs and watches. Here those become collected
errors, so a rebuild can report everything wrong in one pass instead of one
problem per run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..common import ids
from .source import Experiment


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
class Chain:
    """An unbroken run of experiments on one physical sample."""

    material_key: str
    started_at: str
    mass_g: float | None
    base_names: list[str] = field(default_factory=list)

    @property
    def chain_hash(self) -> str:
        return ids.chain_hash(self.material_key, self.started_at)

    @property
    def node_id(self) -> str:
        return ids.chain_id(self.chain_hash)


@dataclass
class IntendedGraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)
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


def build_chains(
    experiments: Iterable[Experiment],
) -> tuple[list[Chain], list[str], list[str]]:
    """Group time-ordered experiments into chains. Returns (chains, warnings, errors).

    A chain breaks when `is_new` is true, meaning a fresh sample was physically
    loaded into the cell. Everything else continues the chain already running.
    """
    ordered = sorted(experiments, key=lambda e: e.started_at)
    chains: list[Chain] = []
    warnings: list[str] = []
    errors: list[str] = []
    current: Chain | None = None

    for exp in ordered:
        material_key = ids.material_key(exp.material)

        if exp.is_new_sample is None:
            # Never guess. A null is_new silently coerced to False would merge
            # two chains that represent different physical samples, and nothing
            # downstream could tell.
            errors.append(
                f"{exp.base_name}: is_new is null. Resolve it in the source "
                "before rebuilding - it decides where chains break."
            )
            continue

        if exp.is_new_sample or current is None:
            current = Chain(
                material_key=material_key,
                started_at=exp.started_at.isoformat(),
                mass_g=exp.mass_g,
            )
            chains.append(current)
        else:
            if current.material_key != material_key:
                # The original pipeline assumed a material change always implies
                # is_new, and so never checked. It is worth checking: a chain
                # spanning two materials is physically impossible, and the graph
                # would present it as one continuous sample history.
                warnings.append(
                    f"{exp.base_name}: continues a chain on a different material "
                    f"({material_key} vs {current.material_key}). is_new is false, "
                    "but the sample must have been changed."
                )
            if (
                exp.mass_g is not None
                and current.mass_g is not None
                and abs(exp.mass_g - current.mass_g) > 1e-9
            ):
                errors.append(
                    f"{exp.base_name}: mass_g {exp.mass_g} disagrees with "
                    f"{current.mass_g} for the chain starting {current.started_at}."
                )

        current.base_names.append(exp.base_name)

    return chains, warnings, errors


def build(
    experiments: Iterable[Experiment],
    adsparams: dict[str, list[dict[str, Any]]] | None = None,
) -> IntendedGraph:
    """Compute the whole data graph the sources imply.

    `adsparams` maps base_name to one property dict per peak, sourced from the
    fit CSVs. Omitted entirely for now - no sample CSV has been seen yet - so
    AdsParams nodes and YIELDS edges are simply absent rather than guessed at.
    """
    experiments = list(experiments)
    adsparams = adsparams or {}
    graph = IntendedGraph()

    for exp in experiments:
        graph.warnings.extend(f"{exp.base_name}: {w}" for w in exp.warnings)

    chains, chain_warnings, chain_errors = build_chains(experiments)
    graph.chains = chains
    graph.warnings.extend(chain_warnings)
    graph.errors.extend(chain_errors)

    seen_materials: set[str] = set()
    by_name = {e.base_name: e for e in experiments}

    for exp in experiments:
        mat_id = ids.material_id(exp.material)
        if mat_id not in seen_materials:
            seen_materials.add(mat_id)
            graph.nodes.append(
                Node(
                    id=mat_id,
                    label="Material",
                    # mass_g is deliberately dropped: it belongs to the chain,
                    # being a property of the loading rather than the formulation.
                    properties={
                        k: v for k, v in exp.material.items() if k != "mass_g"
                    },
                )
            )

        fn_id = ids.filename_id(exp.base_name)
        graph.nodes.append(
            Node(
                id=fn_id,
                label="Filename",
                properties={
                    "base_name": exp.base_name,
                    "datetime": exp.started_at.isoformat(),
                    **exp.flags,
                },
            )
        )
        graph.edges.append(Edge("HAS_EXPERIMENT", mat_id, fn_id))

        step_ids: list[str] = []
        for step in exp.pretreatments:
            index = int(step["step_index"])
            step_id = ids.pretreatment_id(exp.base_name, index)
            step_ids.append(step_id)
            graph.nodes.append(Node(id=step_id, label="Pretreatment", properties=dict(step)))
            # `order` on the edge duplicates `step_index` on the node on purpose,
            # so "give me step N" is one hop and needs no traversal.
            graph.edges.append(Edge("HAS_STEP", fn_id, step_id, {"order": index}))

        for earlier, later in zip(step_ids, step_ids[1:]):
            graph.edges.append(Edge("NEXT_STEP", earlier, later))

        if exp.conditions:
            ec_id = ids.conditions_id(exp.base_name)
            graph.nodes.append(
                Node(id=ec_id, label="ExpConditions", properties=dict(exp.conditions))
            )
            graph.edges.append(Edge("CONDUCTED_UNDER", fn_id, ec_id))
            if step_ids:
                # The procedure runs on from the last pretreatment into the
                # measurement itself, so NEXT_STEP walks the whole thing.
                graph.edges.append(Edge("NEXT_STEP", step_ids[-1], ec_id))

            for peak in adsparams.get(exp.base_name, []):
                ap_id = ids.adsparams_id(exp.base_name, peak["peak_name"])
                graph.nodes.append(Node(id=ap_id, label="AdsParams", properties=dict(peak)))
                graph.edges.append(Edge("YIELDS", ec_id, ap_id))

    for chain in chains:
        graph.nodes.append(
            Node(
                id=chain.node_id,
                label="KineticChain",
                properties={
                    "chain_id": chain.chain_hash,
                    "material_key": chain.material_key,
                    "started_at": chain.started_at,
                    "length": len(chain.base_names),
                    "mass_g": chain.mass_g,
                },
            )
        )
        for base_name in chain.base_names:
            graph.edges.append(
                Edge("IN_CHAIN", ids.filename_id(base_name), chain.node_id)
            )
        for earlier, later in zip(chain.base_names, chain.base_names[1:]):
            graph.edges.append(
                Edge("NEXT_EXP", ids.filename_id(earlier), ids.filename_id(later))
            )

    if not by_name:
        graph.warnings.append("no experiments found - check SOURCE_ROOT")

    return graph
