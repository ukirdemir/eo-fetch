from datetime import UTC, datetime

import pytest

from eo_fetch.backends.nasa import (
    NasaBackend,
    file_details,
    granule_time,
    pick_link,
    split_product,
    version_key,
)
from eo_fetch.models import Query


class FakeGranule(dict):
    def __init__(self, umm, links, megabytes):
        super().__init__({"umm": umm})
        self._links = links
        self._megabytes = megabytes

    def data_links(self):
        return self._links

    def size(self):
        return self._megabytes


def umm_for(name, size=None, checksum=None, begin="2026-09-01T00:00:00.000Z"):
    info = {"Name": name}
    if size is not None:
        info["SizeInBytes"] = size
    if checksum:
        info["Checksum"] = {"Value": checksum, "Algorithm": "SHA-256"}
    return {
        "GranuleUR": name,
        "TemporalExtent": {"RangeDateTime": {"BeginningDateTime": begin}},
        "DataGranule": {"ArchiveAndDistributionInformation": [info]},
    }


class FakeEarthaccess:
    def __init__(self, granules, versions=("06", "07B", "07")):
        self.granules = granules
        self.versions = versions
        self.calls = []

    def search_datasets(self, **kwargs):
        self.calls.append(("datasets", kwargs))
        return [{"umm": {"EntryTitle": "T"}, "meta": {}, "_v": v} for v in self.versions]

    def search_data(self, **kwargs):
        self.calls.append(("data", kwargs))
        return self.granules


class SummaryCollection(dict):
    def __init__(self, version):
        super().__init__({"umm": {"EntryTitle": "IMERG"}})
        self._version = version

    def summary(self):
        return {"short-name": "GPM_3IMERGDL", "version": self._version}


def backend_with(granules, versions=("06", "07B", "07")):
    backend = NasaBackend()
    fake = FakeEarthaccess(granules)
    fake.search_datasets = lambda **kw: [SummaryCollection(v) for v in versions]
    backend._ea = fake
    return backend, fake


def test_helpers():
    assert split_product("GPM_3IMERGDL@07") == ("GPM_3IMERGDL", "07")
    assert split_product("GPM_3IMERGDL") == ("GPM_3IMERGDL", "")
    assert max(["06", "07B", "07"], key=version_key) == "07B"
    assert max(["2.1", "10.0", "9"], key=version_key) == "10.0"
    links = ["https://x/f.nc4.xml", "s3://bucket/f.nc4", "https://x/f.nc4", "https://x/f.png"]
    assert pick_link(links) == "https://x/f.nc4"
    assert pick_link(["https://x/a.xml"]) is None
    umm = umm_for("f.nc4", size=1234, checksum="abc")
    assert file_details(umm, "f.nc4") == (1234, "sha256:abc")
    assert file_details(umm, "other.nc4") == (None, None)
    assert granule_time(umm) == datetime(2026, 9, 1, tzinfo=UTC)


def test_search_builds_items_with_exact_and_approximate_sizes():
    first = FakeGranule(
        umm_for("b.nc4", size=100, checksum="aa", begin="2026-09-02T00:00:00.000Z"),
        ["https://h/b.nc4"],
        0.0001,
    )
    second = FakeGranule(umm_for("a.nc4"), ["https://h/a.nc4"], 2.5)
    backend, fake = backend_with([first, second])
    items = backend.search(
        Query(
            provider="nasa",
            product="GPM_3IMERGDL",
            start=datetime(2026, 9, 1, tzinfo=UTC),
            end=datetime(2026, 9, 3, tzinfo=UTC),
            bbox=(0.0, 1.0, 2.0, 3.0),
        )
    )
    assert [i.key for i in items] == ["a.nc4", "b.nc4"]  # sorted by time
    assert items[0].size is None and items[0].size_hint == 2_500_000
    assert items[1].size == 100 and items[1].checksum == "sha256:aa"
    call = next(args for kind, args in fake.calls if kind == "data")
    assert call["short_name"] == "GPM_3IMERGDL"
    assert call["version"] == "07B"  # newest version chosen
    assert call["temporal"] == ("2026-09-01T00:00:00Z", "2026-09-03T00:00:00Z")
    assert call["bounding_box"] == (0.0, 1.0, 2.0, 3.0)
    assert call["count"] == -1


def test_end_time_is_exclusive():
    days = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    granules = [
        FakeGranule(
            umm_for(f"f{day}.nc4", begin=f"{day}T00:00:00.000Z"), [f"https://h/f{day}.nc4"], 1
        )
        for day in days
    ]
    backend, _ = backend_with(granules)
    items = backend.search(
        Query(
            provider="nasa",
            product="X@1",
            start=datetime(2026, 10, 20, tzinfo=UTC),
            end=datetime(2026, 10, 23, tzinfo=UTC),
        )
    )
    assert [i.key for i in items] == ["f2026-10-20.nc4", "f2026-10-21.nc4", "f2026-10-22.nc4"]


def test_explicit_version_concept_id_and_limit():
    backend, fake = backend_with([])
    backend.search(Query(provider="nasa", product="GPM_3IMERGDF@07", limit=3))
    backend.search(Query(provider="nasa", product="C1234-GES_DISC", limit=1))
    data_calls = [args for kind, args in fake.calls if kind == "data"]
    assert data_calls[0]["version"] == "07" and data_calls[0]["count"] == 3
    assert data_calls[1]["concept_id"] == "C1234-GES_DISC"
    assert "short_name" not in data_calls[1]


def test_search_needs_product_and_a_bound():
    backend, _ = backend_with([])
    with pytest.raises(ValueError, match="--product"):
        backend.search(Query(provider="nasa"))
    with pytest.raises(ValueError, match="--limit"):
        backend.search(Query(provider="nasa", product="GPM_3IMERGDL"))


def test_granules_without_data_links_are_skipped():
    granule = FakeGranule(umm_for("a.nc4"), ["https://h/a.xml"], 1)
    backend, _ = backend_with([granule])
    assert backend.search(Query(provider="nasa", product="X@1", limit=5)) == []


def test_fetch_writes_file_and_explains_403(tmp_path):
    class Response:
        def __init__(self, status, content=b""):
            self.status_code = status
            self._content = content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

        def iter_content(self, size):
            yield self._content

    class Session:
        def __init__(self, status):
            self.status = status

        def get(self, url, **kwargs):
            return Response(self.status, b"data")

    granule = FakeGranule(umm_for("a.nc4"), ["https://h/a.nc4"], 1)
    backend, _ = backend_with([granule])
    item = backend.search(Query(provider="nasa", product="X@1", limit=1))[0]
    backend._session = Session(200)
    target = tmp_path / "a.nc4"
    backend.fetch(item, target)
    assert target.read_bytes() == b"data"
    backend._session = Session(403)
    with pytest.raises(RuntimeError, match="approve"):
        backend.fetch(item, tmp_path / "b.nc4")


def test_collections_need_keyword():
    backend, _ = backend_with([])
    with pytest.raises(ValueError, match="--text"):
        backend.collections("")
    assert backend.collections("imerg")[0][0].startswith("GPM_3IMERGDL@")
