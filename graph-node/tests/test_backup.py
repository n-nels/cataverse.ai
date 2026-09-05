"""The share-drive backup.

The exclusion rules matter more than they look. `_test` and `archive` exist on
the real share but were empty on the copy this was developed against, so the
rule never fired during development. These tests are the only thing standing
between a working exclusion and quietly publishing test data.
"""

from pathlib import Path

from graph_node import backup
from graph_node.common.s3 import StoredObject, content_type_for


def relative(*parts):
    return Path(*parts)


def test_test_directories_are_excluded():
    assert backup.is_excluded(relative("peakFit", "_test", "a.csv"))
    assert backup.is_excluded(relative("peakFit", "_test", "deep", "a.csv"))


def test_archive_directories_are_excluded():
    assert backup.is_excluded(relative("OpusReadParams", "archive", "a.txt"))


def test_marker_matches_as_a_substring_not_only_exactly():
    """A folder named nn1120-3_pd_ceo2_test is still test data.

    The first version required the component to equal `_test`, which would have
    uploaded this. data/source.py had always matched on substring, so the two
    disagreed.
    """
    assert backup.is_excluded(relative("peakFit", "nn1120-3_pd_ceo2_test", "a.csv"))
    assert backup.is_excluded(relative("peakFit", "old_archive_2024", "a.csv"))


def test_exclusion_is_case_insensitive():
    assert backup.is_excluded(relative("peakFit", "_TEST", "a.csv"))
    assert backup.is_excluded(relative("peakFit", "Archive", "a.csv"))


def test_real_folders_are_not_excluded():
    assert backup.is_excluded(relative("peakFit", "nn1120-3_pd_ceo2_004", "a.csv")) is None
    assert backup.is_excluded(relative("OpusConvert_lgRfl", "nn1120-4_pd_ceo2_000", "x.0001")) is None


def test_a_filename_is_never_examined():
    """A file called ..._test.csv is real data; only directories are excluded."""
    assert backup.is_excluded(relative("peakFit", "good", "run_test.csv")) is None
    assert backup.is_excluded(relative("peakFit", "good", "archive.csv")) is None


def make_share(tmp_path: Path):
    """A miniature share drive with one real folder and one excluded one."""
    real = tmp_path / "peakFit" / "nn1120-3_pd_ceo2_004"
    real.mkdir(parents=True)
    (real / "a_CarbonylPeakArea.csv").write_text("x" * 100)
    (real / "a_expParams.json").write_text("{}")

    junk = tmp_path / "peakFit" / "_test"
    junk.mkdir(parents=True)
    (junk / "ignore_me.csv").write_text("y" * 50)

    spectra = tmp_path / "OpusConvert_lgRfl" / "nn1120-3_pd_ceo2_004"
    spectra.mkdir(parents=True)
    (spectra / "a.0000").write_text("z" * 200)
    return tmp_path


def test_plan_mirrors_the_share_path_as_the_key(tmp_path):
    plan = backup.build_plan(make_share(tmp_path), {})
    keys = sorted(c.key for c in plan.to_upload)
    assert keys == [
        "OpusConvert_lgRfl/nn1120-3_pd_ceo2_004/a.0000",
        "peakFit/nn1120-3_pd_ceo2_004/a_CarbonylPeakArea.csv",
        "peakFit/nn1120-3_pd_ceo2_004/a_expParams.json",
    ]


def test_plan_uses_forward_slashes_on_windows(tmp_path):
    plan = backup.build_plan(make_share(tmp_path), {})
    assert all("\\" not in c.key for c in plan.to_upload)


def test_excluded_files_are_counted_not_uploaded(tmp_path):
    plan = backup.build_plan(make_share(tmp_path), {})
    assert plan.excluded == 1
    assert not any("_test" in c.key for c in plan.to_upload)


def test_files_already_in_the_bucket_at_the_same_size_are_skipped(tmp_path):
    share = make_share(tmp_path)
    stored = {
        "peakFit/nn1120-3_pd_ceo2_004/a_CarbonylPeakArea.csv": StoredObject(
            key="peakFit/nn1120-3_pd_ceo2_004/a_CarbonylPeakArea.csv", bytes=100
        )
    }
    plan = backup.build_plan(share, stored)
    assert plan.already_present == 1
    assert "peakFit/nn1120-3_pd_ceo2_004/a_CarbonylPeakArea.csv" not in {
        c.key for c in plan.to_upload
    }


def test_a_size_mismatch_is_re_uploaded(tmp_path):
    share = make_share(tmp_path)
    stored = {
        "peakFit/nn1120-3_pd_ceo2_004/a_CarbonylPeakArea.csv": StoredObject(
            key="peakFit/nn1120-3_pd_ceo2_004/a_CarbonylPeakArea.csv", bytes=999
        )
    }
    plan = backup.build_plan(share, stored)
    candidate = next(
        c for c in plan.to_upload if c.key.endswith("a_CarbonylPeakArea.csv")
    )
    assert candidate.reason == "size differs"


def test_a_missing_root_is_reported_not_ignored(tmp_path):
    """Silently backing up three of four roots is the failure to avoid."""
    plan = backup.build_plan(make_share(tmp_path), {})
    assert set(plan.missing_roots) == {"OpusReadParams", "pressureData"}


def test_spectra_get_a_readable_content_type():
    """`.0000` is not a known type; without this a browser downloads instead
    of reading, and nothing can plot it."""
    assert content_type_for(Path("a.0000")) == "text/plain"
    assert content_type_for(Path("a.csv")) == "text/csv"
    assert content_type_for(Path("a.json")) == "application/json"
    assert content_type_for(Path("a.txt")) == "text/plain"


def test_excluded_files_are_attributed_to_a_directory(tmp_path):
    """A bare count is not enough when exclusions outnumber uploads.

    On the real share 36,742 files were skipped against 33,782 uploaded, and
    the report gave no way to see which directories accounted for it.
    """
    share = make_share(tmp_path)
    archive = share / "OpusConvert_lgRfl" / "archive"
    archive.mkdir(parents=True)
    (archive / "old.0000").write_text("a")
    (archive / "older.0001").write_text("b")

    plan = backup.build_plan(share, {})
    assert plan.excluded == 3
    assert plan.excluded_by_directory == {
        "peakFit/.../_test": 1,
        "OpusConvert_lgRfl/.../archive": 2,
    }


def test_the_report_names_the_excluded_directories(tmp_path):
    plan = backup.build_plan(make_share(tmp_path), {})
    text = backup.render(plan, tmp_path, "some-bucket")
    assert "excluded, by the directory that matched" in text
    assert "_test" in text
