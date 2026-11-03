from datetime import UTC, datetime

import pytest

from eo_fetch.backends.http_index import HttpIndexBackend, parse_index
from eo_fetch.models import Query
from eo_fetch.timeguess import guess_time

ROOT_PAGE = """<html><body><h1>Index of /weather/radar/radolan/yw/</h1><hr><pre>
<a href="../">../</a>
<a href="raa01-yw_10000-2610312200-dwd---bin.hdf5">raa01-yw_10000-2610312200-dwd---bin.hdf5</a> \
31-Oct-2026 22:05:26     27631
<a href="raa01-yw_10000-2610312220-dwd---bin.hdf5">raa01-yw_10000-2610312220-dwd---bin.hdf5</a> \
31-Oct-2026 22:25:30     27800
<a href="notes.txt">notes.txt</a>                  01-Jan-2026 00:00:00     12
<a href="sub/">sub/</a>                            30-Oct-2026 10:00:00         -
</pre><hr></body></html>"""

SUB_PAGE = """<pre>
<a href="../">../</a>
<a href="icon_2026110300_000.grib2">icon_2026110300_000.grib2</a> 03-Nov-2026 02:00:00   100
</pre>"""


class FakeResponse:
    def __init__(self, text="", status=200, content=b""):
        self.text = text
        self.status_code = status
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if url in self.pages:
            page = self.pages[url]
            if isinstance(page, bytes):
                return FakeResponse(content=page)
            return FakeResponse(page)
        return FakeResponse(status=404)


def backend_with(pages):
    backend = HttpIndexBackend(base_url="https://example.org")
    backend._session = FakeSession(pages)
    return backend


def test_parse_index_entries():
    entries = parse_index(ROOT_PAGE)
    assert [e.name for e in entries] == [
        "raa01-yw_10000-2610312200-dwd---bin.hdf5",
        "raa01-yw_10000-2610312220-dwd---bin.hdf5",
        "notes.txt",
        "sub/",
    ]
    assert entries[0].size == 27631
    assert entries[0].modified == datetime(2026, 10, 31, 22, 5, 26, tzinfo=UTC)
    assert entries[3].is_dir
    assert entries[3].size is None


def test_guess_time_dwd_names():
    assert guess_time("x/raa01-yw_10000-2610312220-dwd---bin.hdf5") == datetime(
        2026, 10, 31, 22, 20, tzinfo=UTC
    )
    assert guess_time("icon_2026110300_000.grib2") == datetime(2026, 11, 3, tzinfo=UTC)
    assert guess_time("grids_germany_monthly_202610.asc.gz") == datetime(2026, 10, 1, tzinfo=UTC)


def test_search_time_filter_and_mtime_fallback():
    backend = backend_with({"https://example.org/weather/radar/radolan/yw/": ROOT_PAGE})
    query = Query(provider="dwd", product="weather/radar/radolan/yw")
    items = backend.search(query)
    assert [i.key.rsplit("/", 1)[-1] for i in items] == [
        "notes.txt",
        "raa01-yw_10000-2610312200-dwd---bin.hdf5",
        "raa01-yw_10000-2610312220-dwd---bin.hdf5",
    ]
    assert items[0].time == datetime(2026, 1, 1, tzinfo=UTC)  # modification time
    assert items[1].time == datetime(2026, 10, 31, 22, 0, tzinfo=UTC)  # from the name
    assert backend.folders_seen == ["weather/radar/radolan/yw/sub"]

    filtered = backend.search(
        Query(
            provider="dwd",
            product="weather/radar/radolan/yw",
            start=datetime(2026, 10, 31, 22, 10, tzinfo=UTC),
        )
    )
    assert [i.size for i in filtered] == [27800]


def test_search_text_limit_and_depth():
    backend = backend_with(
        {
            "https://example.org/a/": ROOT_PAGE,
            "https://example.org/a/sub/": SUB_PAGE,
        }
    )
    items = backend.search(
        Query(provider="dwd", product="a", text="*.grib2", params={"depth": "2"})
    )
    assert [i.key for i in items] == ["a/sub/icon_2026110300_000.grib2"]
    assert items[0].url == "https://example.org/a/sub/icon_2026110300_000.grib2"
    assert backend.search(Query(provider="dwd", product="a", limit=1, params={"depth": "2"}))


def test_missing_folder_is_reported():
    backend = backend_with({})
    with pytest.raises(FileNotFoundError):
        backend.search(Query(provider="dwd", product="nope"))


def test_fetch_writes_file(tmp_path):
    backend = backend_with({"https://example.org/a/f.bin": b"abc"})
    items = backend_with({"https://example.org/a/": ROOT_PAGE}).search(
        Query(provider="dwd", product="a")
    )
    item = items[0]
    target = tmp_path / "f.bin"
    backend._session.pages[item.url] = b"abc"
    backend.fetch(item, target)
    assert target.read_bytes() == b"abc"


def test_base_url_required():
    with pytest.raises(ValueError):
        HttpIndexBackend()
