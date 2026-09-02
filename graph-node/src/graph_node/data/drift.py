"""Reference-state drift: RELATIVE_TO and DELTA_FROM.

Ported from `original/knowledge_graph_instructions.txt` §11, where it was
worked out in detail. It lives on the data side despite that filing, because
it is arithmetic on measurements with no knowledge-graph input.

The science, briefly. A kinetic chain walks a sample through a series of
metastable states. Reference experiments are deliberately repeated anchors -
the same script run on the same sample - so they probe whether earlier
operations changed it irreversibly. Two references in one chain need not agree,
and the difference between them *is* the signal. Anything measured between two
references is read against the most recent one before it.

So this layer adds edges only, no nodes: every experiment points back at the
reference it should be interpreted against, and where both sides produced fits,
the numeric differences ride on a parallel edge.
"""

from __future__ import annotations

from typing import Any

from ..common import ids
from .source import Experiment

#: Edge property -> the AdsParams property it is computed from.
#: Deltas are source minus target.
DELTA_PROPERTIES: dict[str, str] = {
    "delta_ka": "pfo_sec_k_a",
    "delta_qe": "pfo_sec_q_e",
    "delta_ks": "pfo_sec_k_s",
    "delta_kp": "pfo_sec_k_p",
    "delta_qinf": "pfo_sec_q_inf",
    "delta_q0": "pfo_sec_q0",
    "delta_time": "time_s",
}


def _deltas(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """source - target, per property. Null wherever either side is missing.

    Deliberately unthresholded: every qualifying pair gets an edge, and whether
    a difference is significant is decided at query time by someone who knows
    the chemistry - not silently at load time.
    """
    out: dict[str, Any] = {}
    for edge_property, node_property in DELTA_PROPERTIES.items():
        a, b = source.get(node_property), target.get(node_property)
        out[edge_property] = (a - b) if (a is not None and b is not None) else None
    return out


def build_drift_edges(
    chains,
    experiments: dict[str, Experiment],
    adsparams: dict[str, list[dict[str, Any]]],
):
    """RELATIVE_TO and DELTA_FROM edges for every chain.

    Returns (edges, warnings). Imports Edge lazily to avoid a circular import
    with build, which calls this.
    """
    from .build import Edge

    edges: list[Edge] = []
    warnings: list[str] = []

    for chain in chains:
        current_reference: str | None = None

        for base_name in chain.base_names:
            experiment = experiments.get(base_name)
            if experiment is None:
                continue

            if current_reference is not None:
                edges.append(
                    Edge(
                        "RELATIVE_TO",
                        ids.filename_id(base_name),
                        ids.filename_id(current_reference),
                    )
                )
                edges.extend(
                    _delta_edges(base_name, current_reference, adsparams)
                )

            # Advance the pointer only after emitting, so a reference is
            # compared against the *previous* reference rather than itself.
            # This is what makes the references form a connected subchain.
            if experiment.flags.get("is_reference") is True:
                current_reference = base_name

        if current_reference is None and chain.base_names:
            # Every experiment in the chain is floating: nothing to interpret
            # any of them against.
            warnings.append(
                f"chain {chain.node_id} ({len(chain.base_names)} experiments) "
                "contains no reference experiment, so it has no drift edges."
            )

    return edges, warnings


def _delta_edges(
    source_base: str,
    target_base: str,
    adsparams: dict[str, list[dict[str, Any]]],
):
    """DELTA_FROM edges between AdsParams sharing a peak name.

    Only emitted where both experiments actually produced fits for the same
    peak - comparing a monomer_sum against a cluster_sum would be meaningless,
    and comparing against a run that produced no CSV is impossible.
    """
    from .build import Edge

    source_peaks = {p["peak_name"]: p for p in adsparams.get(source_base, [])}
    target_peaks = {p["peak_name"]: p for p in adsparams.get(target_base, [])}

    edges: list[Edge] = []
    for peak in sorted(set(source_peaks) & set(target_peaks)):
        edges.append(
            Edge(
                "DELTA_FROM",
                ids.adsparams_id(source_base, peak),
                ids.adsparams_id(target_base, peak),
                _deltas(source_peaks[peak], target_peaks[peak]),
            )
        )
    return edges


def check_targets_are_references(
    edges, experiments: dict[str, Experiment]
) -> list[str]:
    """Every drift edge must point at a reference. Invariant from §11.2.

    Worth asserting rather than assuming: the graph built by the original
    pipeline violates it. Two DELTA_FROM edges target
    20250313_093410_pd_ceo2_000-004, whose is_reference is false - a mislabel
    Nick confirmed on 2026-08-30, corrected in the source and fixed by rebuild.
    """
    problems: list[str] = []
    for edge in edges:
        if edge.type != "RELATIVE_TO":
            continue
        target_base = edge.end.removeprefix("fn_")
        experiment = experiments.get(target_base)
        if experiment is not None and experiment.flags.get("is_reference") is not True:
            problems.append(
                f"{edge.start.removeprefix('fn_')} points at {target_base}, "
                f"whose is_reference is {experiment.flags.get('is_reference')!r}. "
                "Drift targets must be references."
            )
    return problems
