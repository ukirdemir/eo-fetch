from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from eo_fetch.backends.stac import (
    StacBackend,
    asset_filename,
    choose_assets,
    datetime_range,
)
from eo_fetch.models import Query


def fake_item(item_id, when, assets):
    return SimpleNamespace(
        id=item_id,
        datetime=when,
        assets={
            key: SimpleNamespace(href=href, extra_fields=extra)
            for key, (href, extra) in assets.items()
        },
    )


class FakeSearch:
    def __init__(self, items):
        self._items = items

    def items(self):
        return iter(self._items)


class FakeClient:
    def __init__(self, items):
        self.items = items
        self.arguments = None

    def search(self, **arguments):
        self.arguments = arguments
        return FakeSearch(self.items)

    def get_collections(self):
        return [
            SimpleNamespace(id="sentinel-2-l2a", title="Sentinel-2 L2A"),
            SimpleNamespace(id="esa-worldcover", title=None),
        ]


def backend_with(items, **kwargs):
    backend = StacBackend(catalog_url="https://example.org/stac", **kwargs)
    backend._client = FakeClient(items)
    return backend


SCENES = [
    fake_item(
        "S2B_late",
        datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        {
            "B04": ("https://h/late/B04.tif", {"file:size": 2000}),
            "B08": ("https://h/late/B08.tif", {}),
            "SCL": ("https://h/late/SCL.tif", {}),
        },
    ),
    fake_item(
        "S2A_early",
        datetime(2026, 9, 1, 10, 0),
        {
            "B04": ("s3://bucket/early/B04.tif", {}),
            "B08": ("s3://bucket/early/B08.tif", {}),
        },
    ),
]


def test_helpers():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 3, 12, 30, tzinfo=UTC)
    assert datetime_range(start, end) == "2026-09-01T00:00:00Z/2026-09-03T12:30:00Z"
    assert datetime_range(start, None) == "2026-09-01T00:00:00Z/.."
    assert datetime_range(None, None) is None
    assert asset_filename("S2A_x", "B04", "https://h/a/b/T32_B04_10m.tif?sig=1") == "S2A_x_B04.tif"
    assert asset_filename("id", "data", "https://h/a/file.nc.gz") == "id_data.nc.gz"
    assert asset_filename("id", "x", "https://h/a/noext") == "id_x"
    assert choose_assets(["B04", "visual"], [], "i") == ["visual"]
    assert choose_assets(["B04", "B08"], ["B08"], "i") == ["B08"]
    with pytest.raises(ValueError, match="Available"):
        choose_assets(["B04", "B08"], [], "i")
    with pytest.raises(ValueError, match="no asset B99"):
        choose_assets(["B04"], ["B99"], "i")


def test_search_expands_assets_and_sorts_by_time():
    backend = backend_with(SCENES)
    items = backend.search(
        Query(
            provider="p",
            product="sentinel-2-l2a",
            start=datetime(2026, 9, 1, tzinfo=UTC),
            end=datetime(2026, 9, 4, tzinfo=UTC),
            bbox=(10.0, 50.0, 11.0, 51.0),
            params={"assets": "B04,B08"},
        )
    )
    assert [i.key for i in items] == [
        "S2A_early_B04.tif",
        "S2A_early_B08.tif",
        "S2B_late_B04.tif",
        "S2B_late_B08.tif",
    ]
    assert items[0].time == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)  # naive becomes UTC
    assert items[2].size_hint == 2000 and items[2].size is None
    assert items[0].meta == {"item": "S2A_early", "asset": "B04"}
    arguments = backend._client.arguments
    assert arguments["collections"] == ["sentinel-2-l2a"]
    assert arguments["datetime"] == "2026-09-01T00:00:00Z/2026-09-04T00:00:00Z"
    assert arguments["bbox"] == [10.0, 50.0, 11.0, 51.0]


def test_limit_counts_files():
    backend = backend_with(SCENES)
    items = backend.search(Query(provider="p", product="c", limit=3, params={"assets": "B04,B08"}))
    assert len(items) == 3
    assert backend._client.arguments["max_items"] == 3


def test_search_needs_product_and_clear_asset_message():
    backend = backend_with(SCENES)
    with pytest.raises(ValueError, match="--product"):
        backend.search(Query(provider="p"))
    with pytest.raises(ValueError, match="assets="):
        backend.search(Query(provider="p", product="c"))


def test_collections_filter():
    backend = backend_with([])
    assert backend.collections("sentinel") == [("sentinel-2-l2a", "Sentinel-2 L2A")]
    assert len(backend.collections("")) == 2


def test_fetch_https_signs_and_s3_uses_filesystem(tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b"abc"

    class Session:
        def __init__(self):
            self.urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            return Response()

    class FS:
        def __init__(self):
            self.calls = []

        def get_file(self, source, target):
            self.calls.append(source)
            Path(target).write_bytes(b"xyz")

    backend = backend_with(SCENES)
    backend.signed = lambda href: href + "?signed"
    backend._session = Session()
    backend._fs = FS()
    items = backend.search(Query(provider="p", product="c", params={"assets": "B04"}))
    https_item = next(i for i in items if i.url.startswith("https"))
    s3_item = next(i for i in items if i.url.startswith("s3"))
    out = tmp_path / "a.tif"
    backend.fetch(https_item, out)
    assert out.read_bytes() == b"abc"
    assert backend._session.urls == ["https://h/late/B04.tif?signed"]
    out2 = tmp_path / "b.tif"
    backend.fetch(s3_item, out2)
    assert out2.read_bytes() == b"xyz"
    assert backend._fs.calls == ["bucket/early/B04.tif"]


def test_catalog_url_required():
    with pytest.raises(ValueError, match="catalog_url"):
        StacBackend()


def test_cdse_needs_keys(monkeypatch):
    monkeypatch.delenv("CDSE_S3_KEY", raising=False)
    monkeypatch.delenv("CDSE_S3_SECRET", raising=False)
    pytest.importorskip("s3fs")
    backend = StacBackend(catalog_url="https://x", s3_endpoint="https://eodata.example")
    with pytest.raises(RuntimeError, match="CDSE_S3_KEY"):
        backend.filesystem()
