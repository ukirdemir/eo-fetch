"""S3 backend tests with a fake filesystem (no network, no s3fs needed)."""

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eo_fetch.backends.s3 import S3Backend, goes_prefixes, goes_time, guess_time, split_product
from eo_fetch.download import download_items
from eo_fetch.models import Query
from eo_fetch.providers import get_provider

BUCKET = "noaa-goes19/ABI-L2-CMIPC"


def goes_name(hour: int, minute: int, channel: str = "C13") -> str:
    # day of year 258 is 15 September 2026
    return (
        f"OR_ABI-L2-CMIPC-M6{channel}_G19_s2026258{hour:02d}{minute:02d}171"
        f"_e2026258{hour:02d}{minute:02d}584_c2026258{hour:02d}{minute:02d}599.nc"
    )


class FakeFS:
    """Holds a dict of folder -> {file name: payload}; mimics s3fs.ls(detail=True) and open."""

    def __init__(self, folders: dict[str, dict[str, bytes]]) -> None:
        self.folders = folders
        self.listed: list[str] = []

    def ls(self, prefix: str, detail: bool = True):
        self.listed.append(prefix)
        if prefix not in self.folders:
            raise FileNotFoundError(prefix)
        return [
            {"name": prefix + name, "type": "file", "size": len(payload)}
            for name, payload in self.folders[prefix].items()
        ] + [{"name": prefix + "subfolder", "type": "directory", "size": 0}]

    def find(self, prefix: str, maxdepth: int | None = None, detail: bool = True):
        found = {}
        for folder, files in self.folders.items():
            if not folder.startswith(prefix):
                continue
            levels = folder[len(prefix) :].strip("/").count("/") + (1 if folder != prefix else 0)
            if maxdepth is not None and levels + 1 > maxdepth:
                continue
            for name, payload in files.items():
                key = folder + name
                found[key] = {"name": key, "type": "file", "size": len(payload)}
        return found

    def open(self, key: str, mode: str = "rb"):
        folder, name = key.rsplit("/", 1)
        return io.BytesIO(self.folders[folder + "/"][name])


@pytest.fixture
def backend() -> S3Backend:
    folder = f"{BUCKET.replace('/', '/', 1)}/2026/258/12/"
    fake = FakeFS(
        {
            folder: {
                goes_name(12, 0): b"aaaa",
                goes_name(12, 15): b"bbbbbb",
                goes_name(12, 0, "C08"): b"cc",
            }
        }
    )
    s3 = S3Backend()
    s3._fs = fake
    return s3


def test_split_product():
    assert split_product("noaa-goes19/ABI-L2-CMIPC") == ("noaa-goes19", "ABI-L2-CMIPC")
    assert split_product("noaa-gfs-bdp-pds") == ("noaa-gfs-bdp-pds", "")
    with pytest.raises(ValueError):
        split_product("")


def test_goes_time_parses_day_of_year():
    assert goes_time(goes_name(12, 15)) == datetime(2026, 9, 15, 12, 15, 17, tzinfo=UTC)
    assert goes_time("no-time-here.nc") is None


def test_goes_prefixes_cover_every_hour_in_range():
    start = datetime(2026, 9, 15, 11, 30, tzinfo=UTC)
    end = datetime(2026, 9, 15, 13, 10, tzinfo=UTC)
    prefixes = goes_prefixes("noaa-goes19", "ABI-L2-CMIPC", start, end)
    assert prefixes == [
        "noaa-goes19/ABI-L2-CMIPC/2026/258/11/",
        "noaa-goes19/ABI-L2-CMIPC/2026/258/12/",
        "noaa-goes19/ABI-L2-CMIPC/2026/258/13/",
    ]


def test_search_filters_by_time_and_glob_and_skips_missing_folders(backend: S3Backend):
    query = Query(
        provider="noaa",
        product=BUCKET,
        start=datetime(2026, 9, 15, 11, 30, tzinfo=UTC),
        end=datetime(2026, 9, 15, 12, 10, tzinfo=UTC),
        text="*C13*",
    )
    items = backend.search(query)
    assert [item.time.minute for item in items] == [0]
    assert items[0].size == 4
    assert items[0].url.startswith("s3://noaa-goes19/")
    assert len(backend._fs.listed) == 2  # hours 11 (missing) and 12


def test_search_limit_and_sorting(backend: S3Backend):
    query = Query(
        provider="noaa",
        product=BUCKET,
        start=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        end=datetime(2026, 9, 15, 13, 0, tzinfo=UTC),
        limit=2,
    )
    items = backend.search(query)
    assert [item.time.minute for item in items] == [0, 0]
    assert [item.key for item in items] == sorted(item.key for item in items)


def test_access_denied_becomes_a_clear_error_and_cli_exit_code(monkeypatch, capsys):
    from eo_fetch.cli import main

    class DeniedFS:
        def ls(self, prefix: str, detail: bool = True):
            raise PermissionError("Access Denied")

    monkeypatch.setattr(S3Backend, "filesystem", lambda self: DeniedFS())
    code = main(["search", "--provider", "noaa", "--product", "some-bucket/data"])
    assert code == 1
    error = capsys.readouterr().err
    assert error.startswith("error: Access denied listing s3://some-bucket/data/")
    assert "Traceback" not in error


def test_goes_layout_needs_a_time_range(backend: S3Backend):
    with pytest.raises(ValueError, match="start and --end"):
        backend.search(Query(provider="noaa", product=BUCKET))


def test_prefix_layout_lists_one_folder():
    fake = FakeFS({"some-bucket/data/2026/09/": {"x.grib2": b"123"}})
    s3 = S3Backend()
    s3._fs = fake
    query = Query(
        provider="noaa", product="some-bucket/data", params={"prefix": "2026/09"}, text="*.grib2"
    )
    [item] = s3.search(query)
    assert item.key == "some-bucket/data/2026/09/x.grib2"
    assert item.time is None  # no date in the path or name


def test_guess_time_from_model_folders_and_file_names():
    gfs = "noaa-gfs-bdp-pds/gfs.20260915/12/atmos/gfs.t12z.pgrb2.0p25.f003"
    assert guess_time(gfs) == datetime(2026, 9, 15, 12, tzinfo=UTC)
    nexrad = "unidata-nexrad-level2/2026/09/15/KFWS/KFWS20260915_001318_V06"
    assert guess_time(nexrad) == datetime(2026, 9, 15, 0, 13, 18, tzinfo=UTC)
    persiann = "b/data/1983/PERSIANN-CDR_v01r01_19830101_c20140523.nc"
    assert guess_time(persiann) == datetime(1983, 1, 1, tzinfo=UTC)
    assert guess_time("b/x/file_12345678.bin") is None  # year 1234 is not plausible
    assert guess_time("b/x/20261345.txt") is None  # month 13
    assert guess_time("b/x/readme.txt") is None


def test_time_range_filters_files_with_a_guessed_time():
    folders = {"b/d/": {"f_20260101.nc": b"1", "f_20260301.nc": b"2", "notes.txt": b"3"}}
    s3 = S3Backend()
    s3._fs = FakeFS(folders)
    query = Query(
        provider="noaa",
        product="b/d",
        start=datetime(2026, 2, 1, tzinfo=UTC),
        end=datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert [item.key for item in s3.search(query)] == ["b/d/f_20260301.nc"]


def test_empty_folder_reports_its_subfolders_and_depth_finds_the_files():
    folders = {"b/data/": {}, "b/data/2020/": {"a.nc": b"1"}, "b/data/2021/": {"c.nc": b"22"}}
    fake = FakeFS(folders)
    s3 = S3Backend()
    s3._fs = fake
    shallow = s3.search(Query(provider="noaa", product="b/data"))
    assert shallow == []
    assert s3.folders_seen == ["b/data/subfolder"]
    deep = s3.search(Query(provider="noaa", product="b/data", params={"depth": "2"}))
    assert [item.key for item in deep] == ["b/data/2020/a.nc", "b/data/2021/c.nc"]


def test_download_verifies_exact_size(backend: S3Backend, tmp_path: Path):
    query = Query(
        provider="noaa",
        product=BUCKET,
        start=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        end=datetime(2026, 9, 15, 13, 0, tzinfo=UTC),
        text="*C13*",
    )
    items = backend.search(query)
    results = download_items(backend, items, tmp_path)
    assert [r.status for r in results] == ["downloaded", "downloaded"]
    assert sorted(r.size for r in results) == [4, 6]


def test_provider_card_has_goes_aliases_for_three_satellites():
    info = get_provider("noaa")
    assert info.products["goes19-cmip-conus"] == "noaa-goes19/ABI-L2-CMIPC"
    assert info.products["goes16-lightning"] == "noaa-goes16/GLM-L2-LCFA"
    assert info.products["gfs"] == "noaa-gfs-bdp-pds"
    assert info.products["persiann-cdr"] == "noaa-cdr-precip-persiann-pds"
    assert info.auth == "none"
