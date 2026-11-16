"""Pointer nodes built from an S3 listing.

The rule these tests exist to protect: **every object in the bucket is either
modelled or reported.** A file that is silently neither is how the graph and the
bucket drift apart without anyone noticing, and there are 33,786 objects - far
too many to eyeball.
"""

from graph_node.common import ids
from graph_node.common.s3 import StoredObject
from graph_node.common.writer import _identity_value
from graph_node.data import pointers

BASE = "20260329_032106_pd_ceo2_004-010"
OTHER = "20260404_182647_pd_ceo2_004-012"


def listing(*keys):
    return {k: StoredObject(key=k, bytes=100, last_modified="2026-09-05T01:00:00+00:00")
            for k in keys}


def test_a_modelled_kind_becomes_a_rawfile():
    g = pointers.build(listing(f"peakFit/nb/{BASE}_CarbonylPeakArea.csv"))
    node = next(n for n in g.nodes if n.label == "RawFile")
    assert node.properties["kind"] == "CarbonylPeakArea"
    assert node.properties["base_name"] == BASE
    assert node.properties["content_type"] == "text/csv"
    assert node.properties["uploaded_at"] == "2026-09-05T01:00:00+00:00"


def test_the_rawfile_id_is_the_object_key():
    """No prefix and nothing derived, so the writer can round-trip it."""
    key = f"peakFit/nb/{BASE}_CarbonylPeakArea.csv"
    g = pointers.build(listing(key))
    node = next(n for n in g.nodes if n.label == "RawFile")
    assert node.id == key
    assert _identity_value("RawFile", node.id) == key


def test_spectra_collapse_into_one_series_node():
    """One node per series, not per spectrum - 39,000 nodes is the alternative."""
    g = pointers.build(listing(
        f"OpusConvert_lgRfl/nb/{BASE}.0000",
        f"OpusConvert_lgRfl/nb/{BASE}.0001",
        f"OpusConvert_lgRfl/nb/{BASE}.0002",
    ))
    series = [n for n in g.nodes if n.label == "SpectrumSeries"]
    assert len(series) == 1
    assert series[0].properties["count"] == 3
    assert series[0].properties["bytes"] == 300


def test_the_series_prefix_is_a_filename_prefix_not_a_folder():
    """Mirroring the share means one folder holds every run for a sample, so a
    series is selected by a prefix that ends part-way through the filename."""
    g = pointers.build(listing(f"OpusConvert_lgRfl/nb/{BASE}.0000"))
    series = next(n for n in g.nodes if n.label == "SpectrumSeries")
    assert series.properties["prefix"] == f"OpusConvert_lgRfl/nb/{BASE}."
    assert series.properties["prefix"].endswith(".")


def test_two_runs_in_one_folder_stay_separate():
    g = pointers.build(listing(
        f"OpusConvert_lgRfl/nb/{BASE}.0000",
        f"OpusConvert_lgRfl/nb/{OTHER}.0000",
    ))
    assert len({n.id for n in g.nodes if n.label == "SpectrumSeries"}) == 2


def test_out_of_scope_kinds_are_skipped_and_named():
    g = pointers.build(listing(
        f"peakFit/nb/{BASE}_lgrflPeakHeight.csv",
        f"peakFit/nb/{BASE}_subIFGfiles.txt",
        f"peakFit/nb/{BASE}_README.md",
        f"peakFit/nb/{BASE}_expParams.json",
    ))
    assert not g.nodes
    joined = " ".join(g.warnings)
    for kind in ("lgrflPeakHeight", "subIFGfiles", "README", "expParams"):
        assert kind in joined, f"{kind} was skipped without being named"


def test_isotopic_files_are_excluded():
    """The data graph omits them, so the pointers must too."""
    g = pointers.build(listing(
        f"OpusConvert_lgRfl/nb/{BASE}_isoX_3.0000",
        f"OpusReadParams/nb/{BASE}_isoX_3.txt",
    ))
    assert not g.nodes
    assert any("isotopic" in w for w in g.warnings)


def test_the_connectivity_check_object_is_not_data():
    g = pointers.build(listing("_check/connectivity.txt"))
    assert not g.nodes


def test_files_not_named_for_an_experiment_are_reported():
    """Calibration curves and per-sample monomerMax have no Filename to hang
    off. Level 1 has nowhere to put them; saying so is the point."""
    g = pointers.build(listing(
        "peakFit/nb/CalibrationData/nb_calibrationCurve.csv",
        "peakFit/nb/nb_monomerMax.csv",
        "peakFit/.DS_Store",
    ))
    assert not g.nodes
    assert any("not named for an experiment" in w for w in g.warnings)


def test_an_unknown_base_name_is_reported_not_dropped():
    g = pointers.build(
        listing(f"peakFit/nb/{BASE}_CarbonylPeakArea.csv"),
        known_base_names={OTHER},
    )
    assert not g.nodes
    assert any(BASE in w for w in g.warnings)


def test_a_known_base_name_is_modelled_and_attached():
    key = f"peakFit/nb/{BASE}_CarbonylPeakArea.csv"
    g = pointers.build(listing(key), known_base_names={BASE})
    assert len(g.nodes) == 1
    edge = next(e for e in g.edges if e.type == "HAS_RAW_FILE")
    assert edge.start == ids.filename_id(BASE)
    assert edge.end == key


def test_every_object_is_either_modelled_or_reported():
    """The conservation invariant. Nothing may fall between the two.

    Mirrors the real bucket in miniature: modelled files, excluded kinds,
    isotopic runs, spectra, a stray, and the check object.
    """
    import re

    keys = [
        f"peakFit/nb/{BASE}_CarbonylPeakArea.csv",
        f"peakFit/nb/{BASE}_CarbonylFitResidual.csv",
        f"pressureData/nb/{BASE}_pressureLog.csv",
        f"peakFit/nb/{BASE}_lgrflPeakHeight.csv",
        f"peakFit/nb/{BASE}_expParams.json",
        f"OpusReadParams/nb/{BASE}.txt",
        f"OpusConvert_lgRfl/nb/{BASE}.0000",
        f"OpusConvert_lgRfl/nb/{BASE}.0001",
        f"OpusConvert_lgRfl/nb/{BASE}_isoX_1.0000",
        "peakFit/.DS_Store",
        "_check/connectivity.txt",
    ]
    g = pointers.build(listing(*keys))

    reported = sum(
        int(re.search(r"(\d+) object", w).group(1))
        for w in g.warnings
        if "object(s)" in w
    )
    modelled_files = len([n for n in g.nodes if n.label == "RawFile"])
    spectra = sum(n.properties["count"] for n in g.nodes if n.label == "SpectrumSeries")

    assert reported + modelled_files + spectra == len(keys)


def test_the_series_names_its_index_key():
    """The generated file list sits beside the spectra, so it sorts with them
    and needs no second naming convention."""
    g = pointers.build(listing(f"OpusConvert_lgRfl/nb/{BASE}.0000"))
    series = next(n for n in g.nodes if n.label == "SpectrumSeries")
    assert series.properties["index_key"] == f"OpusConvert_lgRfl/nb/{BASE}.index.json"


def test_pointers_are_their_own_scope():
    """Not part of DATA, and this is the test that says why.

    A pointer-only run writes no Material, Filename or Pretreatment. If those
    labels were in its sweep scope it would find every one of them unstamped
    and delete the entire experiment graph - 2,214 nodes - on the first run
    from a machine without the share drive.
    """
    from graph_node.common.ownership import DATA, KNOWLEDGE, POINTERS, check_disjoint

    check_disjoint()
    assert POINTERS.labels == {"RawFile", "SpectrumSeries"}
    for label in ("Material", "Filename", "Pretreatment", "ExpConditions", "AdsParams"):
        assert not POINTERS.owns_label(label), f"POINTERS must not sweep {label}"
    assert not (POINTERS.labels & DATA.labels)
    assert not (POINTERS.labels & KNOWLEDGE.labels)


def test_the_cross_scope_edges_belong_to_pointers():
    """HAS_RAW_FILE starts on a Filename and ends on a RawFile. The loader that
    creates an edge is the one that must be able to sweep it - same rule that
    puts INSTANCE_OF in KNOWLEDGE."""
    from graph_node.common.ownership import DATA, POINTERS

    assert POINTERS.owns_relationship("HAS_RAW_FILE")
    assert POINTERS.owns_relationship("HAS_SPECTRA")
    assert not DATA.owns_relationship("HAS_RAW_FILE")
