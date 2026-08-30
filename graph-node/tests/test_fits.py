"""Reading fitted parameters from a real peak-area CSV.

The fixture is a genuine `_CarbonylPeakArea.csv` off the share drive: 2,120
rows, 20 peaks x 106 time points.
"""

from pathlib import Path

import pytest

from graph_node.data import fits

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "20260825_052349_pd_ceo2_000-027"


@pytest.fixture
def rows():
    return fits.load(BASE, FIXTURES)


def test_only_monomer_sum_is_loaded(rows):
    """The CSV carries 20 peaks; v1 wants one."""
    assert len(rows) == 1
    assert rows[0]["peak_name"] == "monomer_sum"


def test_selects_the_row_with_the_largest_time(rows):
    """The fit as of the end of the experiment, not an intermediate one."""
    assert rows[0]["time_s"] == pytest.approx(187496.767)


def test_every_mapped_property_is_present(rows):
    for prop in fits.COLUMNS.values():
        assert prop in rows[0], prop


def test_fit_values_match_the_source_row(rows):
    row = rows[0]
    assert row["pfo_sec_r2"] == pytest.approx(0.9761680948307307)
    assert row["pfo_sec_k_a"] == pytest.approx(0.00016098631283410715)
    assert row["pfo_sec_q_e"] == pytest.approx(0.7292613764354229)
    assert row["pfo_sec_q0"] == pytest.approx(0.2932220610757348)


def test_nan_becomes_none_not_nan(rows):
    """Neo4j has no NaN.

    Stored, it would be a property not equal to itself, silently breaking every
    comparison against it. The stderr columns are NaN throughout this file.
    """
    row = rows[0]
    for prop in ("pfo_sec_k_a_stderr", "pfo_sec_q_e_stderr", "pfo_sec_k_p_stderr"):
        assert row[prop] is None


def test_zero_is_kept_and_not_confused_with_missing(rows):
    """pfo_sec_q_inf is legitimately 0.0 here - falsy, but present."""
    assert rows[0]["pfo_sec_q_inf"] == 0.0
    assert rows[0]["pfo_sec_q_inf"] is not None


def test_missing_csv_returns_empty_not_an_error():
    """Normal for a run that was started and abandoned."""
    assert fits.load("does_not_exist", FIXTURES) == []


def test_number_parsing_edge_cases():
    assert fits._number("") is None
    assert fits._number("   ") is None
    assert fits._number(None) is None
    assert fits._number("nan") is None
    assert fits._number("inf") is None
    assert fits._number("not a number") is None
    assert fits._number("0") == 0.0
    assert fits._number(" 1.5 ") == 1.5


def test_load_all_finds_files_beneath_a_root():
    found = fits.load_all([BASE, "missing"], FIXTURES)
    assert set(found) == {BASE}
    assert found[BASE][0]["peak_name"] == "monomer_sum"


def test_widening_the_peak_filter_needs_no_schema_change(monkeypatch):
    """AdsParams is keyed on (base_name, peak_name) already."""
    monkeypatch.setattr(fits, "LOADED_PEAKS", frozenset({"monomer_sum", "cluster_sum"}))
    rows = fits.load(BASE, FIXTURES)
    assert {r["peak_name"] for r in rows} == {"monomer_sum", "cluster_sum"}
