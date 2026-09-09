"""Where the rebuild reads from.

Both stores must behave identically as far as everything downstream can tell,
because the rebuild deletes: if the S3 store enumerated even slightly
differently from the local one, the difference would show up as a sweep.
"""

from pathlib import PurePosixPath

import pytest

from graph_node.data import fits, source
from graph_node.data.store import LocalStore, Ref, S3Store

JSON = '{"base_name": "b", "datetime": "2026-03-29T03:21:06", "material": {}, "filename_flags": {}}'


class FakeS3:
    """Just enough client for the store: get_object returning bytes."""

    def __init__(self, objects: dict[str, str]):
        self.objects = objects
        self.reads: list[str] = []

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3's spelling
        self.reads.append(Key)

        class Body:
            def __init__(self, text):
                self._text = text

            def read(self):
                return self._text.encode("utf-8")

        return {"Body": Body(self.objects[Key])}


def make_local(tmp_path):
    folder = tmp_path / "peakFit" / "nb"
    folder.mkdir(parents=True)
    (folder / "20260329_032106_x-001_expParams.json").write_text(JSON)
    (folder / "20260329_032106_x-001_CarbonylPeakArea.csv").write_text("a,b\n1,2\n")
    junk = tmp_path / "peakFit" / "_test"
    junk.mkdir(parents=True)
    (junk / "20260101_000000_y-001_expParams.json").write_text(JSON)
    return LocalStore(tmp_path)


def make_s3():
    objects = {
        "peakFit/nb/20260329_032106_x-001_expParams.json": JSON,
        "peakFit/nb/20260329_032106_x-001_CarbonylPeakArea.csv": "a,b\n1,2\n",
        "peakFit/_test/20260101_000000_y-001_expParams.json": JSON,
    }
    return S3Store(FakeS3(objects), "bucket", {k: object() for k in objects})


def test_both_stores_find_the_same_relative_paths(tmp_path):
    local = {str(r.relative) for r in make_local(tmp_path).find("_expParams.json")}
    remote = {str(r.relative) for r in make_s3().find("_expParams.json")}
    assert local == remote


def test_both_stores_exclude_the_same_files(tmp_path):
    """The _test folder must be dropped by both, or a rebuild from one source
    would sweep away what the other had just written."""
    local = source.discover(make_local(tmp_path))
    remote = source.discover(make_s3())
    assert [str(r.relative) for r in local.included] == [
        str(r.relative) for r in remote.included
    ]
    assert len(local.excluded) == len(remote.excluded) == 1


def test_the_s3_store_reads_an_object(tmp_path):
    store = make_s3()
    ref = store.find("_expParams.json")[0]
    assert store.read_text(ref) == JSON
    assert store.client.reads == [str(ref.relative)]


def test_an_empty_listing_is_not_a_usable_store():
    """Guarded in the CLI too. An empty source sweeps the whole graph."""
    assert not S3Store(FakeS3({}), "bucket", {}).exists()


def test_fits_load_all_reads_only_the_csvs_that_exist():
    """One GetObject per experiment that has a fit, none for those that do not.

    Roughly one run in twenty here is abandoned with no CSV; fetching for those
    would be wasted round trips against a bucket.
    """
    store = make_s3()
    fits.load_all(["20260329_032106_x-001", "nonexistent-run"], store)
    assert store.client.reads == [
        "peakFit/nb/20260329_032106_x-001_CarbonylPeakArea.csv"
    ]


def test_fits_parse_is_shared_by_both_stores():
    """One selection rule, not two. The largest Time (s) per wanted peak."""
    text = (
        "Peak_Name,Time (s),pfo-sec_k_a_s-1\n"
        "monomer_sum,10,0.5\n"
        "monomer_sum,99,0.9\n"
        "cluster_sum,50,0.1\n"
    )
    rows = fits.parse(text)
    assert len(rows) == 1
    assert rows[0]["peak_name"] == "monomer_sum"
    assert rows[0]["time_s"] == 99.0
    assert rows[0]["pfo_sec_k_a"] == 0.9


def test_a_ref_prints_as_its_relative_path():
    ref = Ref(handle="anything", relative=PurePosixPath("peakFit/nb/x.json"))
    assert str(ref) == "peakFit/nb/x.json"
    assert ref.name == "x.json"


def test_a_local_root_that_does_not_exist_is_reported(tmp_path):
    assert not LocalStore(tmp_path / "nope").exists()


def test_a_few_unreadable_sources_are_tolerated():
    """A corrupt file is a real thing, and its experiment should leave."""
    from graph_node.common.rebuild import systemic_read_failure

    assert systemic_read_failure(0, 299) is None
    assert systemic_read_failure(5, 299) is None


def test_wholesale_read_failure_refuses_the_rebuild():
    """The case observed on 2026-09-08: S3 as the source with a write-only key.

    All 299 sources failed GetObject, so nothing was built, and the plan
    offered to delete all 2,179 nodes and called itself applyable. The sweep's
    own threshold would have aborted it, but a dry run should never have
    reported that plan as worth applying in the first place.
    """
    from graph_node.common.rebuild import systemic_read_failure

    message = systemic_read_failure(299, 299)
    assert message is not None
    assert "299 of 299" in message
    assert systemic_read_failure(100, 299) is not None
