"""The write path, tested against a recording session rather than a database.

The queries themselves are separately validated against live Aura with EXPLAIN
(see the commit that added this file); these tests pin the behaviour that
EXPLAIN cannot see - what gets grouped, what ends up in the payload, and which
key each label is matched on.
"""

import pytest

from graph_node.common import ids, writer
from graph_node.common.rebuild import RUN_PROPERTY
from graph_node.data.build import Edge, Node


class FakeResult:
    def consume(self):
        return None


class RecordingSession:
    """Captures queries instead of running them."""

    def __init__(self):
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return FakeResult()

    def queries_containing(self, needle):
        return [q for q, _ in self.calls if needle in q]


@pytest.fixture
def session():
    return RecordingSession()


def test_constraints_cover_every_identity_property(session):
    created = writer.ensure_constraints(session)
    assert len(created) == len(ids.IDENTITY)
    for label, (prop, _) in ids.IDENTITY.items():
        assert any(
            f"(n:{label})" in q and f"n.`{prop}` IS UNIQUE" in q
            for q, _ in session.calls
        ), label


def test_constraints_are_idempotent(session):
    writer.ensure_constraints(session)
    assert all("IF NOT EXISTS" in q for q, _ in session.calls)


def test_nodes_are_replaced_not_merged(session):
    """SET n = props, never +=.

    `+=` would leave pressure_meas_g1 sitting alongside the new
    pressure_meas_mfld forever. A rebuild has to mean the node ends up exactly
    as the source describes it.
    """
    writer.write_nodes(session, [Node("mat_x", "Material", {"metal": "pd"})], "R1")
    query = session.queries_containing("MERGE")[0]
    assert "SET n = row.props" in query
    assert "+=" not in query


def test_every_node_is_stamped(session):
    writer.write_nodes(session, [Node("mat_x", "Material", {"metal": "pd"})], "R1")
    query, params = session.calls[0]
    assert f"SET n.`{RUN_PROPERTY}` = $run_id" in query
    assert params["run_id"] == "R1"


def test_identity_property_is_included_in_the_payload(session):
    """Otherwise SET n = props strips the key the node was matched on."""
    writer.write_nodes(session, [Node("mat_x", "Material", {"metal": "pd"})], "R1")
    _, params = session.calls[0]
    assert params["rows"][0]["props"]["id"] == "mat_x"


def test_filename_is_keyed_on_base_name_with_the_prefix_stripped(session):
    writer.write_nodes(
        session, [Node("fn_abc", "Filename", {"base_name": "abc"})], "R1"
    )
    query, params = session.calls[0]
    assert "MERGE (n:Filename {`base_name`: row.key})" in query
    assert params["rows"][0]["key"] == "abc"


def test_chain_is_keyed_on_chain_id_with_the_prefix_stripped(session):
    writer.write_nodes(
        session, [Node("kc_deadbeef", "KineticChain", {"chain_id": "deadbeef"})], "R1"
    )
    query, params = session.calls[0]
    assert "MERGE (n:KineticChain {`chain_id`: row.key})" in query
    assert params["rows"][0]["key"] == "deadbeef"


def test_nodes_are_grouped_by_label(session):
    writer.write_nodes(
        session,
        [
            Node("mat_a", "Material", {}),
            Node("mat_b", "Material", {}),
            Node("fn_x", "Filename", {"base_name": "x"}),
        ],
        "R1",
    )
    assert len(session.calls) == 2


def test_large_writes_are_batched(session):
    nodes = [Node(f"mat_{i}", "Material", {}) for i in range(writer.BATCH_SIZE + 10)]
    written = writer.write_nodes(session, nodes, "R1")
    assert written == len(nodes)
    assert len(session.calls) == 2


def test_relationships_match_endpoints_on_their_own_identity(session):
    writer.write_relationships(
        session,
        [Edge("HAS_EXPERIMENT", "mat_x", "fn_abc")],
        {"mat_x": "Material", "fn_abc": "Filename"},
        "R1",
    )
    query, params = session.calls[0]
    assert "MATCH (a:Material {`id`: row.start})" in query
    assert "MATCH (b:Filename {`base_name`: row.end})" in query
    assert params["rows"][0] == {"start": "mat_x", "end": "abc", "props": {}}


def test_relationship_properties_are_written(session):
    writer.write_relationships(
        session,
        [Edge("HAS_STEP", "fn_abc", "pre_abc_1", {"order": 1})],
        {"fn_abc": "Filename", "pre_abc_1": "Pretreatment"},
        "R1",
    )
    query, params = session.calls[0]
    assert "SET r = row.props" in query
    assert f"SET r.`{RUN_PROPERTY}` = $run_id" in query
    assert params["rows"][0]["props"] == {"order": 1}


def test_relationships_are_grouped_by_type_and_endpoint_labels(session):
    writer.write_relationships(
        session,
        [
            Edge("HAS_EXPERIMENT", "mat_x", "fn_a"),
            Edge("HAS_EXPERIMENT", "mat_x", "fn_b"),
            Edge("IN_CHAIN", "fn_a", "kc_1"),
        ],
        {
            "mat_x": "Material",
            "fn_a": "Filename",
            "fn_b": "Filename",
            "kc_1": "KineticChain",
        },
        "R1",
    )
    assert len(session.calls) == 2


def test_edge_to_an_unbuilt_node_is_dropped_not_written(session):
    written = writer.write_relationships(
        session, [Edge("HAS_EXPERIMENT", "mat_x", "fn_missing")], {"mat_x": "Material"}, "R1"
    )
    assert written == 0
    assert session.calls == []
