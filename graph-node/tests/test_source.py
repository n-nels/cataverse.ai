"""Parsing real experiment files.

The two fixtures are genuine `_expParams.json` files off the share drive, one
from each end of the dataset (2025-02 and 2026-08). They are checked in
deliberately: the whole point is to test against what the instruments actually
write rather than against an inferred shape.
"""

import json
from pathlib import Path

import pytest

from graph_node.common import ids
from graph_node.data import source

FIXTURES = Path(__file__).parent / "fixtures"
OLD = FIXTURES / "20250218_063825_pd_ceo2_000-034_expParams.json"
NEW = FIXTURES / "20260825_052349_pd_ceo2_000-027_expParams.json"


@pytest.fixture(params=[OLD, NEW], ids=["2025", "2026"])
def experiment(request):
    return source.load(request.param)


def test_both_files_parse(experiment):
    assert experiment.base_name
    assert experiment.started_at.year in (2025, 2026)
    assert len(experiment.pretreatments) == 4


def test_base_name_matches_the_filename(experiment):
    assert experiment.source_path.name.startswith(experiment.base_name)


def test_datetime_matches_the_base_name_prefix(experiment):
    """The base name encodes YYYYMMDD_HHMMSS; the datetime field must agree."""
    assert experiment.started_at.strftime("%Y%m%d_%H%M%S") == experiment.base_name[:15]


def test_pressure_uses_the_semantic_names_not_gauge_numbers():
    """Source files use mfld/cell. g1/g2 exists only in the database.

    Confirmed against both fixtures, which span 18 months - so no dual-spelling
    handling is needed in the loader.
    """
    for path in (OLD, NEW):
        raw = json.loads(path.read_text())
        blocks = [*raw["pretreatments"], raw["exp_conditions"]]
        for block in blocks:
            assert "pressure_meas_mfld" in block
            assert "pressure_meas_cell" in block
            assert "pressure_meas_g1" not in block
            assert "pressure_meas_g2" not in block


def test_numbers_are_normalised_to_float(experiment):
    """Guards the mixed-type problem: the raw files disagree with each other.

    2025 has `temp: 600` and `rate: 20` (ints); 2026 has `450.0` and `20.0`.
    Left alone, Neo4j would type the same property INTEGER on some nodes and
    FLOAT on others.
    """
    for step in experiment.pretreatments:
        for key in ("temp", "rate", "duration"):
            assert isinstance(step[key], float), f"{key} is {type(step[key])}"


def test_booleans_survive_normalisation():
    """bool is a subclass of int, so a careless float() would turn it into 0.0."""
    exp = source.load(NEW)
    assert exp.pretreatments[0]["chiller"] is False
    assert exp.flags["exp_success"] is True


def test_mass_g_is_read_from_material_but_belongs_to_the_chain(experiment):
    assert experiment.mass_g is not None
    assert experiment.mass_g == experiment.material["mass_g"]


def test_material_id_is_stable_across_the_dataset():
    assert ids.material_id(source.load(OLD).material) == "mat_pd_0p0339_ceo2_54"
    # A third sample, absent from the database as of 2026-08-29.
    assert ids.material_id(source.load(NEW).material) == "mat_pd_0p06645_ceo2_54"


def test_support_sa_stays_an_int_so_ids_do_not_shift():
    """support_sa is part of the material id, where 54 and 54.0 differ.

    Normalisation must not reach into it. If this fails, every Material node
    in the graph is orphaned.
    """
    for path in (OLD, NEW):
        assert ids.material_id(source.load(path).material).endswith("_54")


def test_missing_step_index_is_warned_and_skipped(tmp_path):
    """The hollow-node bug, caught at the source.

    pre_20250802_073857_pd_ceo2_003-001_1 is in the database with an id and no
    other properties, because a step shaped like this was loaded silently.
    """
    raw = json.loads(OLD.read_text())
    raw["pretreatments"][0].pop("step_index")
    path = tmp_path / "x_expParams.json"
    path.write_text(json.dumps(raw))

    exp = source.load(path)
    assert len(exp.pretreatments) == 3
    assert any("step_index" in w for w in exp.warnings)


def test_unparseable_file_raises_rather_than_returning_junk(tmp_path):
    path = tmp_path / "bad_expParams.json"
    path.write_text("{not json")
    with pytest.raises(source.SourceError):
        source.load(path)


def test_missing_required_key_names_what_is_missing(tmp_path):
    path = tmp_path / "bad_expParams.json"
    path.write_text(json.dumps({"base_name": "x"}))
    with pytest.raises(source.SourceError, match="datetime"):
        source.load(path)


def test_discover_finds_files_and_sorts_them(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("b", "a"):
        (tmp_path / "sub" / f"{name}{source.SUFFIX}").write_text("{}")
    (tmp_path / "unrelated.txt").write_text("x")

    found = source.discover(tmp_path)
    assert [p.name for p in found] == [f"a{source.SUFFIX}", f"b{source.SUFFIX}"]


def test_step_index_stays_an_integer(experiment):
    """It counts steps; there is no step 1.5.

    The first live rebuild floated it, which left step_index as 1.0 while the
    redundant `order` on the HAS_STEP edge stayed an integer, and made the
    dashboard render "step 1.0" - its label code interpolates without rounding.
    """
    for step in experiment.pretreatments:
        assert isinstance(step["step_index"], int), type(step["step_index"])
        assert not isinstance(step["step_index"], bool)


def test_step_index_survives_a_float_in_the_source(tmp_path):
    raw = json.loads(NEW.read_text())
    raw["pretreatments"][0]["step_index"] = 1.0
    path = tmp_path / "x_expParams.json"
    path.write_text(json.dumps(raw))
    assert source.load(path).pretreatments[0]["step_index"] == 1


def test_measurements_are_still_floated(experiment):
    """Only ordinals are integers; temperatures and rates stay floats."""
    step = experiment.pretreatments[0]
    assert isinstance(step["temp"], float)
    assert isinstance(step["rate"], float)
