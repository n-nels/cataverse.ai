"""Building the intended graph from parsed experiments."""

from datetime import datetime
from pathlib import Path

import pytest

from graph_node.common import ids
from graph_node.common.ownership import DATA
from graph_node.data import build, source

FIXTURES = Path(__file__).parent / "fixtures"
OLD = FIXTURES / "20250218_063825_pd_ceo2_000-034_expParams.json"
NEW = FIXTURES / "20260825_052349_pd_ceo2_000-027_expParams.json"


def make(base_name, when, *, is_new, mass_g=0.037, loading=0.0339, steps=2):
    """A minimal Experiment, for chain logic that does not need real files."""
    return source.Experiment(
        base_name=base_name,
        started_at=datetime.fromisoformat(when),
        material={
            "metal": "pd",
            "metal_loading": loading,
            "support": "ceo2",
            "support_sa": 54,
            "mass_g": mass_g,
        },
        flags={"is_new": is_new, "exp_success": True, "has_csv": True},
        pretreatments=[{"step_index": i, "temp": 400.0} for i in range(1, steps + 1)],
        conditions={"temp": 45.0},
        source_path=f"{base_name}_expParams.json",
    )


def test_is_new_starts_a_chain():
    chains, _, errors = build.build_chains(
        [
            make("a", "2025-01-01T00:00:00", is_new=True),
            make("b", "2025-01-02T00:00:00", is_new=False),
            make("c", "2025-01-03T00:00:00", is_new=True),
        ]
    )
    assert not errors
    assert [c.base_names for c in chains] == [["a", "b"], ["c"]]


def test_chains_follow_time_not_file_order():
    chains, _, _ = build.build_chains(
        [
            make("late", "2025-01-03T00:00:00", is_new=False),
            make("first", "2025-01-01T00:00:00", is_new=True),
        ]
    )
    assert chains[0].base_names == ["first", "late"]


def test_null_is_new_is_an_error_not_a_guess():
    """Coercing null to False would merge two physically distinct samples."""
    _, _, errors = build.build_chains(
        [
            make("a", "2025-01-01T00:00:00", is_new=True),
            make("b", "2025-01-02T00:00:00", is_new=None),
        ]
    )
    assert any("is_new is null" in e for e in errors)


def test_mass_disagreement_within_a_chain_is_an_error():
    _, _, errors = build.build_chains(
        [
            make("a", "2025-01-01T00:00:00", is_new=True, mass_g=0.037),
            make("b", "2025-01-02T00:00:00", is_new=False, mass_g=0.017),
        ]
    )
    assert any("mass_g" in e for e in errors)


def test_material_change_without_is_new_is_warned():
    """The original pipeline assumed this could not happen and never checked.

    A chain spanning two materials is physically impossible - the sample must
    have been swapped - and the graph would show it as one continuous history.
    """
    _, warnings, _ = build.build_chains(
        [
            make("a", "2025-01-01T00:00:00", is_new=True, loading=0.0339),
            make("b", "2025-01-02T00:00:00", is_new=False, loading=0.06645),
        ]
    )
    assert any("different material" in w for w in warnings)


def test_all_produced_labels_and_types_are_owned_by_the_data_scope():
    """The ownership boundary, checked against what the builder actually emits.

    If the builder ever produces something DATA does not own, the sweep will
    not clean it up and it accumulates silently.
    """
    graph = build.build([source.load(OLD), source.load(NEW)])
    for node in graph.nodes:
        assert DATA.owns_label(node.label), node.label
    for edge in graph.edges:
        assert DATA.owns_relationship(edge.type), edge.type


def test_material_is_emitted_once_per_distinct_sample():
    graph = build.build([source.load(OLD), source.load(NEW)])
    materials = [n for n in graph.nodes if n.label == "Material"]
    assert len(materials) == 2
    assert {m.id for m in materials} == {
        "mat_pd_0p0339_ceo2_54",
        "mat_pd_0p06645_ceo2_54",
    }


def test_mass_g_is_moved_off_material_onto_the_chain():
    graph = build.build([source.load(OLD)])
    material = next(n for n in graph.nodes if n.label == "Material")
    chain = next(n for n in graph.nodes if n.label == "KineticChain")
    assert "mass_g" not in material.properties
    assert chain.properties["mass_g"] == pytest.approx(0.0369)


def test_pretreatments_are_chained_and_run_into_the_conditions():
    exp = source.load(OLD)
    graph = build.build([exp])
    next_step = [e for e in graph.edges if e.type == "NEXT_STEP"]
    # 4 steps -> 3 links between them, plus one into ExpConditions.
    assert len(next_step) == 4
    assert next_step[-1].end == ids.conditions_id(exp.base_name)


def test_has_step_carries_the_order_property():
    graph = build.build([source.load(OLD)])
    orders = sorted(e.properties["order"] for e in graph.edges if e.type == "HAS_STEP")
    assert orders == [1, 2, 3, 4]


def test_no_conditions_means_no_conditions_node():
    """Aborted runs legitimately have no exp_conditions."""
    exp = make("x", "2025-01-01T00:00:00", is_new=True)
    aborted = source.Experiment(
        base_name=exp.base_name,
        started_at=exp.started_at,
        material=exp.material,
        flags={"is_new": True, "exp_success": False, "has_csv": False},
        pretreatments=exp.pretreatments,
        conditions={},
        source_path=exp.source_path,
    )
    graph = build.build([aborted])
    assert not [n for n in graph.nodes if n.label == "ExpConditions"]
    assert not [e for e in graph.edges if e.type == "CONDUCTED_UNDER"]


def test_adsparams_absent_when_no_fits_supplied():
    graph = build.build([source.load(OLD)])
    assert not [n for n in graph.nodes if n.label == "AdsParams"]


def test_adsparams_attach_to_the_conditions_node():
    exp = source.load(OLD)
    graph = build.build(
        [exp],
        adsparams={exp.base_name: [{"peak_name": "monomer_sum", "pfo_sec_r2": 0.99}]},
    )
    ads = next(n for n in graph.nodes if n.label == "AdsParams")
    assert ads.id == ids.adsparams_id(exp.base_name, "monomer_sum")
    yields = next(e for e in graph.edges if e.type == "YIELDS")
    assert yields.start == ids.conditions_id(exp.base_name)
    assert yields.end == ads.id


def test_next_exp_links_consecutive_experiments_in_one_chain():
    graph = build.build(
        [
            make("a", "2025-01-01T00:00:00", is_new=True),
            make("b", "2025-01-02T00:00:00", is_new=False),
            make("c", "2025-01-03T00:00:00", is_new=True),
        ]
    )
    next_exp = [(e.start, e.end) for e in graph.edges if e.type == "NEXT_EXP"]
    # a->b only: c starts a new chain, so nothing links b to it.
    assert next_exp == [(ids.filename_id("a"), ids.filename_id("b"))]
