"""The data/knowledge boundary, enforced rather than intended."""

import pytest

from graph_node.common.ownership import ALL_SCOPES, DATA, KNOWLEDGE, check_disjoint


def test_scopes_do_not_overlap():
    check_disjoint()


def test_delta_from_belongs_to_data():
    """DELTA_FROM is arithmetic on AdsParams, so it is data, not knowledge.

    It shipped in knowledge.cypher in the original pipeline. This is the
    regression test for that specific mistake.
    """
    assert DATA.owns_relationship("DELTA_FROM")
    assert DATA.owns_relationship("RELATIVE_TO")
    assert not KNOWLEDGE.owns_relationship("DELTA_FROM")


@pytest.mark.parametrize(
    "label",
    ["Material", "Filename", "Pretreatment", "ExpConditions", "AdsParams", "KineticChain"],
)
def test_measured_labels_belong_to_data(label):
    assert DATA.owns_label(label)
    assert not KNOWLEDGE.owns_label(label)


@pytest.mark.parametrize(
    "label", ["ChemConcept", "ChemSpecies", "PyFunction", "ModelParameter", "KineticModel"]
)
def test_authored_labels_belong_to_knowledge(label):
    assert KNOWLEDGE.owns_label(label)
    assert not DATA.owns_label(label)


def test_every_label_in_the_live_graph_is_claimed():
    """Every label the graph actually has must have an owner.

    An unclaimed label is one no sweep will ever touch, so it would silently
    accumulate orphans. This list is the labels present in Aura as of
    2026-08-29; update it deliberately when the schema grows.
    """
    live = {
        "AdsParams", "ChemConcept", "ChemSpecies", "ExpConditions", "Filename",
        "KineticChain", "KineticModel", "Material", "ModelParameter",
        "Pretreatment", "PyFunction",
    }
    claimed = set().union(*(s.labels for s in ALL_SCOPES))
    assert live - claimed == set(), f"unclaimed labels: {sorted(live - claimed)}"
