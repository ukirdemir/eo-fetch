"""EUMETSAT backend tests with a fake Data Store (no network, no eumdac needed)."""

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eo_fetch.backends import get_backend
from eo_fetch.backends.eumetsat import EumetsatBackend, bbox_to_wkt, kib_to_bytes
from eo_fetch.cli import main
from eo_fetch.downloader import download_items
from eo_fetch.models import Query
from eo_fetch.registry import get_provider


class FakeProduct:
    def __init__(self, ident: str, sensing: datetime, payload: bytes = b"zipdata") -> None:
        self.ident, self.sensing_start, self.payload, self.size = ident, sensing, payload, 182847

    def __str__(self) -> str:
        return self.ident

    def open(self):
        return io.BytesIO(self.payload)


class FakeCollection:
    def __init__(self, ident: str, title: str, products: list[FakeProduct]) -> None:
        self.ident, self.title, self.products, self.arguments = ident, title, products, {}

    def __str__(self) -> str:
        return self.ident

    def search(self, **arguments):
        self.arguments = arguments
        return iter(self.products)


class FakeStore:
    def __init__(self) -> None:
        self.seviri = FakeCollection(
            "EO:EUM:DAT:MSG:HRSEVIRI",
            "High Rate SEVIRI Level 1.5 Image Data - MSG - 0 degree",
            [
                FakeProduct("B", datetime(2026, 9, 1, 0, 15)),
                FakeProduct("A", datetime(2026, 9, 1, 0, 0)),
                FakeProduct("C", datetime(2026, 9, 1, 0, 30)),
            ],
        )
        self.fci = FakeCollection("EO:EUM:DAT:0665", "FCI Level 1c High Resolution", [])
        self.collections = [self.seviri, self.fci]

    def get_collection(self, ident: str) -> FakeCollection:
        return next(c for c in self.collections if str(c) == ident)

    def get_product(self, product_id: str, collection_id: str) -> FakeProduct:
        products = self.get_collection(collection_id).products
        return next(p for p in products if str(p) == product_id)


@pytest.fixture
def backend() -> EumetsatBackend:
    eumetsat = EumetsatBackend()
    eumetsat._store = FakeStore()
    return eumetsat


def test_bbox_to_wkt_closes_the_ring():
    wkt = bbox_to_wkt((-14.0, -4.0, 18.0, 26.0))
    assert wkt == "POLYGON((-14.0 -4.0, 18.0 -4.0, 18.0 26.0, -14.0 26.0, -14.0 -4.0))"


def test_search_sorts_converts_time_and_passes_arguments(backend: EumetsatBackend):
    query = Query(
        provider="eumetsat",
        product="EO:EUM:DAT:MSG:HRSEVIRI",
        start=datetime(2026, 9, 1, tzinfo=UTC),
        end=datetime(2026, 9, 2, tzinfo=UTC),
        bbox=(-14, -4, 18, 26),
    )
    items = backend.search(query)
    assert [item.key for item in items] == ["A", "B", "C"]
    assert items[0].time == datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    arguments = backend._store.seviri.arguments
    assert arguments["dtstart"] == query.start
    assert arguments["geo"].startswith("POLYGON((")


def test_limit_keeps_earliest_with_a_time_range_and_newest_without(backend: EumetsatBackend):
    # the fake answers in the order B, A, C (not sorted); the real service answers newest first
    bounded = Query(
        provider="eumetsat",
        product="EO:EUM:DAT:MSG:HRSEVIRI",
        start=datetime(2026, 9, 1, tzinfo=UTC),
        limit=2,
    )
    assert [item.key for item in backend.search(bounded)] == ["A", "B"]
    open_ended = Query(provider="eumetsat", product="EO:EUM:DAT:MSG:HRSEVIRI", limit=2)
    assert [item.key for item in backend.search(open_ended)] == ["A", "B"]


def test_missing_product_is_an_error(backend: EumetsatBackend):
    with pytest.raises(ValueError, match="collection id"):
        backend.search(Query(provider="eumetsat"))


def test_size_hint_is_kibibytes_and_not_used_for_verification(backend: EumetsatBackend):
    items = backend.search(Query(provider="eumetsat", product="EO:EUM:DAT:MSG:HRSEVIRI"))
    assert items[0].size is None
    assert items[0].size_hint == 182847 * 1024
    assert items[0].expected_size == 182847 * 1024
    assert kib_to_bytes("not a number") is None


def test_collections_filter_by_text(backend: EumetsatBackend):
    assert [c[0] for c in backend.collections("seviri")] == ["EO:EUM:DAT:MSG:HRSEVIRI"]
    assert len(backend.collections()) == 2


def test_fetch_writes_the_product(backend: EumetsatBackend, tmp_path: Path):
    items = backend.search(Query(provider="eumetsat", product="EO:EUM:DAT:MSG:HRSEVIRI"))
    results = download_items(backend, items[:1], tmp_path)
    assert results[0].status == "downloaded"
    assert (tmp_path / "A").read_bytes() == b"zipdata"


def test_connection_limit_is_conservative():
    assert get_backend("eumetsat").max_connections == 2


def test_provider_card_aliases_point_to_collections():
    info = get_provider("eumetsat")
    assert info.products["seviri"] == "EO:EUM:DAT:MSG:HRSEVIRI"
    assert info.attribution == "Contains modified EUMETSAT data"
    assert info.auth == "licence"


def test_cli_lists_providers_and_reports_missing_credentials(monkeypatch, capsys):
    monkeypatch.delenv("EUMETSAT_KEY", raising=False)
    monkeypatch.delenv("EUMETSAT_SECRET", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("/nonexistent-home"))
    assert main(["providers"]) == 0
    assert "eumetsat" in capsys.readouterr().out
    assert main(["doctor", "--provider", "eumetsat"]) == 1
    assert "credentials: FAILED" in capsys.readouterr().out
