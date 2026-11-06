from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import eo_fetch as eof


def make_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    for name in ("a.nc", "b.nc", "c.txt"):
        (source / name).write_text(f"content of {name}")
    return source


def test_public_names():
    for name in ("search", "download", "open", "plot", "verify", "providers", "login", "doctor"):
        assert callable(getattr(eof, name))
    assert eof.Item and eof.Query and eof.Result and eof.Results


def test_providers_and_provider_cards():
    names = {info.name for info in eof.providers()}
    assert {"dwd", "eumetsat", "nasa", "esgf", "cdse"} <= names
    assert eof.provider("dwd").name == "dwd"


def test_search_download_verify_roundtrip(tmp_path):
    source = make_source(tmp_path)
    found = eof.search("local", root=source, text="*.nc")
    assert [item.key for item in found] == ["a.nc", "b.nc"]
    assert isinstance(found, eof.Results) and found.megabytes > 0

    dest = tmp_path / "dest"
    results = eof.download(found, dest)
    assert [r.status for r in results] == ["downloaded", "downloaded"]
    assert (dest / "manifest.json").is_file()
    assert eof.verify(dest / "manifest.json") == []

    (dest / "a.nc").write_text("tampered")
    assert eof.verify(dest / "manifest.json", root=dest)


def test_slices_and_where_keep_the_download_context(tmp_path):
    found = eof.search("local", root=make_source(tmp_path), text="*.nc")
    first = found[:1]
    assert isinstance(first, eof.Results) and len(first) == 1
    only_b = found.where(lambda item: item.key == "b.nc")
    results = only_b.download(tmp_path / "out", manifest=tmp_path / "m.json")
    assert [r.item.key for r in results] == ["b.nc"]
    assert (tmp_path / "m.json").is_file()


def test_download_needs_a_search_result_and_ignores_empty_results(tmp_path):
    found = eof.search("local", root=make_source(tmp_path), text="*.nc")
    with pytest.raises(TypeError, match=r"eof\.search"):
        eof.download(list(found), tmp_path / "out")
    assert eof.download(found.where(lambda item: False), tmp_path / "out") == []
    assert not (tmp_path / "out").exists()


def test_search_accepts_strings_dates_and_lists(tmp_path):
    found = eof.search(
        "local",
        root=make_source(tmp_path),
        text="*.nc",
        start="2000-01-01",
        end=date(2100, 1, 1),
        limit=1,
    )
    assert len(found) == 1
    assert found.query.start == datetime(2000, 1, 1, tzinfo=UTC)
    assert found.query.end == datetime(2100, 1, 1, tzinfo=UTC)


def test_search_params_dict_lists_and_unknown_names(tmp_path):
    found = eof.search("local", params={"root": str(make_source(tmp_path))}, text="*.nc")
    assert len(found) == 2
    with pytest.raises(ValueError, match="Unknown --param"):
        eof.search("local", root=str(tmp_path), nonsense="x")
    assert eof.api.param_text(["tas", "pr"]) == "tas,pr"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        eof.search("no-such-provider")


def test_plot_a_dataset_needs_an_output():
    with pytest.raises(ValueError, match="output"):
        eof.plot(object())


def test_open_a_netcdf_file(tmp_path):
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    path = tmp_path / "x.nc"
    xr.Dataset({"t": (("lat", "lon"), np.zeros((2, 3)))}).to_netcdf(path)
    with eof.open(path) as dataset:
        assert dataset["t"].shape == (2, 3)
