from datetime import UTC, datetime
from pathlib import Path

import pytest

from eo_fetch.backends.esgf import (
    EsgfBackend,
    item_from_info,
    normalise_checksum,
    split_values,
    to_datetime,
)
from eo_fetch.models import Item, Query

SHA = "ab" * 32


class NoSearchResults(Exception):
    pass


class FakeCatalog:
    def __init__(self, infos=None, fail=False):
        self.infos = infos or []
        self.fail = fail
        self.searches = []

    def search(self, **kwargs):
        if self.fail:
            raise NoSearchResults()
        self.searches.append(kwargs)
        return self

    def _get_file_info(self, quiet=False):
        return self.infos


def info(name, start=None, links=("https://node.example/a/" + "f.nc",), size=10, checksum=SHA):
    return {
        "key": "ds1",
        "path": Path("CMIP6/x") / name,
        "HTTPServer": list(links),
        "size": size,
        "checksum": checksum,
        "checksum_type": "SHA256",
        "file_start": start,
    }


def backend_with(catalog):
    backend = EsgfBackend()
    backend._catalog = catalog
    return backend


def test_split_values():
    assert split_values("tas") == "tas"
    assert split_values("tas, pr") == ["tas", "pr"]


def test_normalise_checksum_accepts_known_digests_only():
    assert normalise_checksum(SHA, "SHA256") == f"sha256:{SHA}"
    assert normalise_checksum(SHA, "SHA-256") == f"sha256:{SHA}"
    assert normalise_checksum("1220" + SHA, None) == f"sha256:{SHA}"
    assert normalise_checksum("ab" * 16, "md5") == "md5:" + "ab" * 16
    assert normalise_checksum("zz" * 32, "sha256") is None
    assert normalise_checksum(SHA, "weird") is None
    assert normalise_checksum(None, "sha256") is None


def test_to_datetime_makes_aware_and_ignores_missing():
    assert to_datetime(datetime(2000, 1, 1)) == datetime(2000, 1, 1, tzinfo=UTC)
    assert to_datetime(None) is None
    assert to_datetime(float("nan")) is None


def test_item_from_info_needs_a_link():
    item = item_from_info("esgf", "CMIP6", info("tas_1850.nc", links=("u1", "u2")))
    assert item.key == "tas_1850.nc" and item.url == "u1"
    assert item.meta["mirrors"] == "u1 u2"
    assert item.size == 10 and item.checksum == f"sha256:{SHA}"
    assert item_from_info("esgf", "CMIP6", info("x.nc", links=())) is None


def test_search_builds_facets_and_sorts_items():
    catalog = FakeCatalog(
        [
            info("b_2000.nc", start=datetime(2000, 1, 1)),
            info("a_1990.nc", start=datetime(1990, 1, 1)),
            info("a_1990.nc", start=datetime(1990, 1, 1)),  # duplicate path
        ]
    )
    items = backend_with(catalog).search(
        Query(
            provider="esgf",
            product="CMIP6",
            start=datetime(1990, 1, 1, tzinfo=UTC),
            params={"variable_id": "tas,pr", "experiment_id": "historical"},
        )
    )
    assert [i.key for i in items] == ["a_1990.nc", "b_2000.nc"]
    call = catalog.searches[0]
    assert call["project"] == "CMIP6"
    assert call["variable_id"] == ["tas", "pr"] and call["experiment_id"] == "historical"
    assert call["file_start"] == "1990-01-01 00:00:00"


def test_search_returns_nothing_when_index_finds_nothing():
    backend = backend_with(FakeCatalog(fail=True))
    assert backend.search(Query(provider="esgf", params={"variable_id": "tas"})) == []


def test_search_validation():
    backend = backend_with(FakeCatalog())
    with pytest.raises(ValueError, match="facet"):
        backend.search(Query(provider="esgf"))
    with pytest.raises(ValueError, match="bbox"):
        backend.search(Query(provider="esgf", bbox=(0, 0, 1, 1), params={"variable_id": "tas"}))


class FakeResponse:
    def __init__(self, ok, data=b""):
        self.ok = ok
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if not self.ok:
            raise OSError("503")

    def iter_content(self, size):
        yield self.data


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.responses[url]


def test_fetch_falls_back_to_next_mirror(tmp_path):
    backend = EsgfBackend()
    backend._session = FakeSession({"u1": FakeResponse(False), "u2": FakeResponse(True, b"data")})
    item = Item(provider="esgf", product="CMIP6", key="f.nc", meta={"mirrors": "u1 u2"})
    target = tmp_path / "f.nc.part"
    backend.fetch(item, target)
    assert target.read_bytes() == b"data"
    assert backend._session.urls == ["u1", "u2"]


def test_fetch_reports_when_all_mirrors_fail(tmp_path):
    backend = EsgfBackend()
    backend._session = FakeSession({"u1": FakeResponse(False)})
    item = Item(provider="esgf", product="CMIP6", key="f.nc", meta={"mirrors": "u1"})
    with pytest.raises(OSError, match="All 1 mirrors failed"):
        backend.fetch(item, tmp_path / "f.nc.part")
