"""Reference-state drift edges.

The rules come from original/knowledge_graph_instructions.txt section 11,
which worked them out carefully. The subtle one is step 3b: the pointer
advances *after* the edge is emitted, so a reference compares against the
previous reference rather than itself.
"""

from datetime import datetime

import pytest

from graph_node.common import ids
from graph_node.data import build, drift, source


def make(base_name, day, *, is_new=False, is_reference=False):
    return source.Experiment(
        base_name=base_name,
        started_at=datetime(2025, 1, day),
        material={
            "metal": "pd",
            "metal_loading": 0.0339,
            "support": "ceo2",
            "support_sa": 54,
            "mass_g": 0.037,
        },
        flags={
            "is_new": is_new,
            "is_reference": is_reference,
            "exp_success": True,
            "has_csv": True,
        },
        pretreatments=[{"step_index": 1, "temp": 400.0}],
        conditions={"temp": 45.0},
        source_path=f"{base_name}.json",
    )


def fits(**values):
    base = {
        "peak_name": "monomer_sum",
        "pfo_sec_k_a": 0.0,
        "pfo_sec_q_e": 0.0,
        "pfo_sec_k_s": 0.0,
        "pfo_sec_k_p": 0.0,
        "pfo_sec_q_inf": 0.0,
        "pfo_sec_q0": 0.0,
        "time_s": 0.0,
    }
    return [base | values]


def relative_to(graph):
    return [
        (e.start.removeprefix("fn_"), e.end.removeprefix("fn_"))
        for e in graph.edges
        if e.type == "RELATIVE_TO"
    ]


def test_experiments_point_at_the_most_recent_prior_reference():
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
            make("b", 3),
        ]
    )
    assert relative_to(graph) == [("a", "r1"), ("b", "r1")]


def test_a_reference_points_at_the_previous_reference_not_itself():
    """Section 11.2 step 3b: emit, then advance the pointer.

    Getting this backwards would make every reference point at itself, and the
    subchain of anchors - the whole point of the layer - would not exist.
    """
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
            make("r2", 3, is_reference=True),
        ]
    )
    assert ("r2", "r1") in relative_to(graph)
    assert ("r2", "r2") not in relative_to(graph)


def test_the_pointer_moves_on_to_the_newer_reference():
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("r2", 2, is_reference=True),
            make("a", 3),
        ]
    )
    assert ("a", "r2") in relative_to(graph)
    assert ("a", "r1") not in relative_to(graph)


def test_nothing_before_the_first_reference_gets_an_edge():
    """Those experiments occupy a metastable state with no anchor to compare to."""
    graph = build.build(
        [
            make("a", 1, is_new=True),
            make("b", 2),
            make("r1", 3, is_reference=True),
        ]
    )
    assert relative_to(graph) == []


def test_drift_edges_never_cross_a_chain_boundary():
    """A new sample means the previous reference describes different material."""
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
            make("r2", 3, is_new=True, is_reference=True),
            make("b", 4),
        ]
    )
    assert relative_to(graph) == [("a", "r1"), ("b", "r2")]


def test_chain_with_no_reference_is_warned_about():
    graph = build.build([make("a", 1, is_new=True), make("b", 2)])
    assert any("no reference experiment" in w for w in graph.warnings)


def test_delta_from_is_computed_as_source_minus_target():
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
        ],
        adsparams={
            "r1": fits(pfo_sec_k_a=1.0, time_s=100.0),
            "a": fits(pfo_sec_k_a=1.5, time_s=250.0),
        },
    )
    delta = next(e for e in graph.edges if e.type == "DELTA_FROM")
    assert delta.start == ids.adsparams_id("a", "monomer_sum")
    assert delta.end == ids.adsparams_id("r1", "monomer_sum")
    assert delta.properties["delta_ka"] == pytest.approx(0.5)
    assert delta.properties["delta_time"] == pytest.approx(150.0)


def test_delta_is_null_where_either_side_is_missing():
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
        ],
        adsparams={
            "r1": fits(pfo_sec_k_a=None),
            "a": fits(pfo_sec_k_a=1.5),
        },
    )
    delta = next(e for e in graph.edges if e.type == "DELTA_FROM")
    assert delta.properties["delta_ka"] is None


def test_no_delta_edge_without_fits_on_both_sides():
    """RELATIVE_TO still exists - the experiment happened, it just has no fits."""
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
        ],
        adsparams={"a": fits(pfo_sec_k_a=1.5)},
    )
    assert relative_to(graph) == [("a", "r1")]
    assert not [e for e in graph.edges if e.type == "DELTA_FROM"]


def test_deltas_are_only_computed_between_matching_peaks():
    """Comparing a monomer_sum against a cluster_sum would be meaningless."""
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
        ],
        adsparams={
            "r1": fits(peak_name="cluster_sum"),
            "a": fits(peak_name="monomer_sum"),
        },
    )
    assert not [e for e in graph.edges if e.type == "DELTA_FROM"]


def test_no_thresholding_a_zero_delta_still_gets_an_edge():
    """Significance is a query-time decision, not a load-time one."""
    graph = build.build(
        [
            make("r1", 1, is_new=True, is_reference=True),
            make("a", 2),
        ],
        adsparams={"r1": fits(pfo_sec_k_a=1.0), "a": fits(pfo_sec_k_a=1.0)},
    )
    delta = next(e for e in graph.edges if e.type == "DELTA_FROM")
    assert delta.properties["delta_ka"] == 0.0


def test_target_that_is_not_a_reference_is_reported():
    """The invariant that the live graph violates.

    Two DELTA_FROM edges target 20250313_093410_pd_ceo2_000-004, whose
    is_reference is false - a mislabel Nick confirmed and corrected in source.
    """
    experiments = {"a": make("a", 2), "bad": make("bad", 1)}
    edges = [build.Edge("RELATIVE_TO", "fn_a", "fn_bad")]
    problems = drift.check_targets_are_references(edges, experiments)
    assert len(problems) == 1
    assert "bad" in problems[0]


def test_a_correct_reference_target_raises_nothing():
    experiments = {"a": make("a", 2), "r1": make("r1", 1, is_reference=True)}
    edges = [build.Edge("RELATIVE_TO", "fn_a", "fn_r1")]
    assert drift.check_targets_are_references(edges, experiments) == []
