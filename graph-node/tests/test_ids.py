"""The id builders are pinned, not just tested.

Every value below was read out of the live Aura database on 2026-08-29 and
verified to round-trip: rebuilding the id from the node's own properties
reproduces the id already stored on it, for all 1,830 data nodes (the single
exception is a known hollow node, see spec.md Data integrity).

If one of these assertions starts failing, the change is a migration - it
orphans every existing node of that label - not a refactor. Read the module
docstring in graph_node.common.ids before touching it.
"""

from graph_node.common import ids

# The 4.983 wt% Pd on ceria sample, as stored.
MATERIAL = {
    "metal": "pd",
    "metal_loading": 0.04983,
    "support": "ceo2",
    "support_sa": 54,
    "notebook": "nn1120-3",
    "mfldVol": 0.201552,
}

BASE = "20250802_073857_pd_ceo2_003-001"


def test_material_id_matches_the_database():
    assert ids.material_id(MATERIAL) == "mat_pd_0p04983_ceo2_54"


def test_material_key_ignores_properties_outside_the_natural_key():
    """notebook and mfldVol describe the sample but do not identify it."""
    variant = MATERIAL | {"notebook": "different", "mfldVol": 9.99}
    assert ids.material_id(variant) == ids.material_id(MATERIAL)


def test_support_sa_type_changes_the_id():
    """54 and 54.0 produce different ids - the loader must not retype silently.

    This is not hypothetical tidiness: `.` becomes `p`, so an int-to-float
    change rewrites the id from `..._54` to `..._54p0` and orphans the node.
    """
    as_float = MATERIAL | {"support_sa": 54.0}
    assert ids.material_id(as_float) == "mat_pd_0p04983_ceo2_54p0"
    assert ids.material_id(as_float) != ids.material_id(MATERIAL)


def test_per_experiment_ids():
    assert ids.filename_id(BASE) == f"fn_{BASE}"
    assert ids.conditions_id(BASE) == f"ec_{BASE}"
    assert ids.pretreatment_id(BASE, 2) == f"pre_{BASE}_2"


def test_adsparams_id_carries_the_peak_name():
    assert ids.adsparams_id(BASE) == f"ap_{BASE}_monomer_sum"
    assert ids.adsparams_id(BASE, "cluster_sum") == f"ap_{BASE}_cluster_sum"


def test_chain_hash_is_stable_and_short():
    h = ids.chain_hash("pd|0.04983|ceo2|54", "2025-08-02T07:38:57")
    assert h == ids.chain_hash("pd|0.04983|ceo2|54", "2025-08-02T07:38:57")
    assert len(h) == 12
    assert ids.chain_id(h) == f"kc_{h}"


def test_chain_hash_distinguishes_start_times():
    a = ids.chain_hash("pd|0.04983|ceo2|54", "2025-08-02T07:38:57")
    b = ids.chain_hash("pd|0.04983|ceo2|54", "2025-08-03T07:38:57")
    assert a != b
