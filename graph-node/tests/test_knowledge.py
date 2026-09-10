"""The knowledge graph and its attachment to the data graph.

Built against the real YAML in `graph-node/knowledge/`, not fixtures - it is
hand-authored content in the repo, so the checked-in files are the truth.
"""

from datetime import datetime

import pytest

from graph_node.common import ids
from graph_node.common.model import IntendedGraph, Node
from graph_node.common.ownership import KNOWLEDGE
from graph_node.data import build as dbuild
from graph_node.data import source as dsource
from graph_node.knowledge import build as kbuild
from graph_node.knowledge import source as ksource


@pytest.fixture(scope="module")
def yamls():
    return ksource.load()


def experiment(base_name, *, is_reference=False, gases=("RoughPump",), rate=20.0,
               duration=0.0, exp_gas=("13CO",)):
    return dsource.Experiment(
        base_name=base_name,
        started_at=datetime(2025, 1, 1),
        material={"metal": "pd", "metal_loading": 0.0339, "support": "ceo2",
                  "support_sa": 54, "mass_g": 0.037},
        flags={"is_new": True, "is_reference": is_reference,
               "exp_type": "adsorption", "exp_success": True, "has_csv": True},
        pretreatments=[{"step_index": 1, "gas": list(gases), "rate": rate,
                        "duration": duration, "temp": 450.0}],
        conditions={"gas": list(exp_gas), "temp": 45.0},
        source_path=f"{base_name}.json",
    )


def build_both(experiments, yamls, adsparams=None):
    data = dbuild.build(experiments, adsparams=adsparams)
    return data, kbuild.build(yamls, data)


def concepts_for(knowledge, node_id):
    return {
        e.end.removeprefix("cc_")
        for e in knowledge.edges
        if e.type == "INSTANCE_OF" and e.start == node_id
    }


def test_vocabulary_matches_the_stored_graph(yamls):
    """Counts verified against live Aura on 2026-09-02.

    Level 2 added 2026-09-10: 5 DataFileType, 65 DataColumn (63 named plus 2
    patterns) and 3 PeakGroup. They describe formats, so unlike everything
    above them these counts do not move as experiments accumulate - if this
    assertion changes, someone edited the YAML.
    """
    knowledge = kbuild.build(yamls, IntendedGraph())
    assert knowledge.nodes_by_label() == {
        "ChemConcept": 15, "ChemSpecies": 8, "PyFunction": 5,
        "KineticModel": 1, "ModelParameter": 6,
        "DataFileType": 5, "DataColumn": 65, "PeakGroup": 3,
    }
    counts = knowledge.edges_by_type()
    assert counts["SUBTYPE_OF"] == 8
    assert counts["PARAMETER_OF"] == 6
    assert counts["IMPLEMENTS"] == 12
    assert counts["USES_SPECIES"] == 12
    assert counts["HAS_COLUMN"] == 65
    assert counts["MEASURES"] == 6
    assert counts["HAS_GROUP"] == 6


def test_everything_produced_is_owned_by_the_knowledge_scope(yamls):
    data, knowledge = build_both([experiment("a")], yamls)
    for node in knowledge.nodes:
        assert KNOWLEDGE.owns_label(node.label), node.label
    for edge in knowledge.edges:
        assert KNOWLEDGE.owns_relationship(edge.type), edge.type


def test_drift_edges_are_not_emitted_here(yamls):
    """DELTA_FROM and RELATIVE_TO belong to the data graph.

    The original pipeline emitted them from the knowledge loader. Two loaders
    writing the same edges with different run stamps means whichever sweeps
    last deletes the other's work.
    """
    data, knowledge = build_both([experiment("a")], yamls)
    types = set(knowledge.edges_by_type())
    assert "DELTA_FROM" not in types
    assert "RELATIVE_TO" not in types


def test_evacuation_rule(yamls):
    _, k = build_both([experiment("a", gases=("TurboPump",))], yamls)
    assert "evacuation" in concepts_for(k, ids.pretreatment_id("a", 1))


def test_chemistry_rule_maps_gas_to_concepts(yamls):
    """CO2 is both an oxidiser and a carbonation agent - both fire."""
    _, k = build_both([experiment("a", gases=("CO2",))], yamls)
    assert {"oxidation", "carbonation"} <= concepts_for(k, ids.pretreatment_id("a", 1))


def test_all_matching_rules_fire_not_just_the_first(yamls):
    """A step that ramps while dosing O2 is both a ramp and an oxidation."""
    _, k = build_both([experiment("a", gases=("O2",), rate=20.0)], yamls)
    assert {"oxidation", "thermal_ramp"} <= concepts_for(k, ids.pretreatment_id("a", 1))


def test_soak_needs_zero_rate_and_positive_duration(yamls):
    _, soak = build_both([experiment("a", rate=0.0, duration=30.0)], yamls)
    assert "thermal_soak" in concepts_for(soak, ids.pretreatment_id("a", 1))

    _, ramping = build_both([experiment("b", rate=5.0, duration=30.0)], yamls)
    assert "thermal_soak" not in concepts_for(ramping, ids.pretreatment_id("b", 1))


def test_conditions_become_an_adsorption_measurement(yamls):
    _, k = build_both([experiment("a")], yamls)
    assert "adsorption_measurement" in concepts_for(k, ids.conditions_id("a"))


def test_reference_filenames_are_marked_and_others_are_not(yamls):
    _, k = build_both(
        [experiment("ref", is_reference=True), experiment("plain")], yamls
    )
    assert concepts_for(k, ids.filename_id("ref")) == {"reference_state"}
    assert concepts_for(k, ids.filename_id("plain")) == set()


def test_adsparams_inherit_reference_state_from_their_experiment(yamls):
    fits = {"ref": [{"peak_name": "monomer_sum", "pfo_sec_r2": 0.9}],
            "plain": [{"peak_name": "monomer_sum", "pfo_sec_r2": 0.9}]}
    _, k = build_both(
        [experiment("ref", is_reference=True), experiment("plain")],
        yamls, adsparams=fits,
    )
    assert "reference_state" in concepts_for(k, ids.adsparams_id("ref"))
    assert "reference_state" not in concepts_for(k, ids.adsparams_id("plain"))


def test_every_adsparams_is_fit_by_the_model(yamls):
    fits = {"a": [{"peak_name": "monomer_sum", "pfo_sec_r2": 0.9}]}
    _, k = build_both([experiment("a")], yamls, adsparams=fits)
    fit_by = [e for e in k.edges if e.type == "FIT_BY"]
    assert len(fit_by) == 1
    assert fit_by[0].start == ids.adsparams_id("a")
    assert fit_by[0].end == ids.kinetic_model_id("pfo_secondary")


def test_a_rule_that_never_fires_is_warned_about(yamls):
    """Dead rules and broken rules look identical without this."""
    _, k = build_both([experiment("a", gases=("RoughPump",), rate=20.0)], yamls)
    # No reference experiment in this set, so F1 and A1 cannot fire.
    assert any("F1_reference" in w for w in k.warnings)


def test_a_mapping_naming_an_undefined_concept_is_an_error(yamls):
    broken = ksource.KnowledgeSource(
        concepts=yamls.concepts, species=yamls.species,
        py_functions=yamls.py_functions, model=yamls.model,
        parameters=yamls.parameters,
        mappings={"py_to_concept": {"clean_surface": ["not_a_real_concept"]}},
    )
    knowledge = kbuild.build(broken, IntendedGraph())
    assert any("not_a_real_concept" in e for e in knowledge.errors)


def test_attachment_uses_the_intended_data_not_the_database(yamls):
    """New data nodes get their concepts in the same rebuild that creates them.

    Attaching to stored data instead would leave the overlay one run behind -
    which is exactly what happened after the first live data rebuild, when 190
    new Pretreatment nodes had no INSTANCE_OF edges.
    """
    data = IntendedGraph()
    data.nodes.append(
        Node(ids.pretreatment_id("brand_new", 1), "Pretreatment",
             {"gas": ["O2"], "rate": 0.0, "duration": 10.0})
    )
    knowledge = kbuild.build(yamls, data)
    assert concepts_for(knowledge, ids.pretreatment_id("brand_new", 1)) == {
        "oxidation", "thermal_soak",
    }


def test_level2_columns_are_keyed_on_the_file_type_too(yamls):
    """`Peak_Name` and `File` each appear in two file types. Keying a column on
    its name alone would collapse them into one node and lose a whole file
    type's description."""
    knowledge = kbuild.build(yamls, IntendedGraph())
    columns = [n for n in knowledge.nodes if n.label == "DataColumn"]
    ids_seen = [n.id for n in columns]
    assert len(ids_seen) == len(set(ids_seen)), "DataColumn ids must be unique"
    peak_name = sorted(n.id for n in columns if n.properties.get("name") == "Peak_Name")
    assert peak_name == [
        "CarbonylPeakArea.Peak_Name",
        "CarbonylPeakFitParams.Peak_Name",
    ]


def test_a_matrix_file_type_describes_its_columns_by_pattern(yamls):
    """The fit matrices carry one column per spectrum and the set differs
    between experiments, so there is no list that stays true for the next
    file."""
    knowledge = kbuild.build(yamls, IntendedGraph())
    patterns = [
        n for n in knowledge.nodes
        if n.label == "DataColumn" and n.properties.get("pattern")
    ]
    assert len(patterns) == 2
    for node in patterns:
        assert node.properties["matches"]
        assert node.properties["optional"] is True


def test_measures_reaches_a_parameter_that_exists(yamls):
    """The join a question depends on. `plot the adsorption rate constant`
    resolves through MEASURES onto the ModelParameter holding k_a."""
    knowledge = kbuild.build(yamls, IntendedGraph())
    node_ids = {n.id for n in knowledge.nodes}
    measures = [e for e in knowledge.edges if e.type == "MEASURES"]
    assert measures
    for edge in measures:
        assert edge.end in node_ids, f"MEASURES points at missing {edge.end}"
    ends = {e.end for e in measures}
    assert "mp_pfo_secondary_k_a" in ends


def test_a_measures_naming_an_unknown_parameter_is_reported(yamls):
    """Not dropped. A join that silently does not exist is the failure mode -
    the question still gets an answer, just not from the data it names."""
    import dataclasses

    broken = dataclasses.replace(
        yamls,
        file_types=[{
            "name": "Made Up",
            "columns": [{"name": "c", "role": "fitted", "measures": "not_a_parameter"}],
        }],
    )
    knowledge = kbuild.build(broken, IntendedGraph())
    assert any("not_a_parameter" in w for w in knowledge.warnings)
    assert not [e for e in knowledge.edges if e.type == "MEASURES"]


def test_of_type_links_a_rawfile_to_its_format(yamls):
    from graph_node.common.model import Node

    pointer_graph = IntendedGraph()
    pointer_graph.nodes.append(
        Node(id="peakFit/nb/x_CarbonylPeakArea.csv", label="RawFile",
             properties={"kind": "CarbonylPeakArea"})
    )
    pointer_graph.nodes.append(
        Node(id="peakFit/nb/x_Unmodelled.csv", label="RawFile",
             properties={"kind": "Unmodelled"})
    )
    knowledge = kbuild.build(yamls, IntendedGraph(), pointer_graph)
    of_type = [e for e in knowledge.edges if e.type == "OF_TYPE"]
    assert len(of_type) == 1
    assert of_type[0].end == "dft_CarbonylPeakArea"
    assert any("Unmodelled" in w for w in knowledge.warnings)


def test_peak_groups_carry_both_isotope_numberings(yamls):
    """Everything is collected with 13CO, but a reader looking up the
    literature works in 12CO. Both numberings, or the question asked one way
    finds nothing."""
    knowledge = kbuild.build(yamls, IntendedGraph())
    groups = {n.properties["definition"][:0] or n.id: n
              for n in knowledge.nodes if n.label == "PeakGroup"}
    monomer = next(n for n in knowledge.nodes
                   if n.label == "PeakGroup" and n.id == "pg_monomer_sum")
    assert monomer.properties["peaks_13co"] == [2093, 2103, 2113, 2125]
    assert monomer.properties["peaks_12co"] == [2143, 2153, 2163, 2175]
    assert monomer.properties["shift_cm1"] == -50
