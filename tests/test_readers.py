"""Offline reader tests: tiny synthetic files in each format, no network."""

from datetime import datetime

import pytest

from eo_fetch import readers
from eo_fetch.readers import NoReaderError, detect_format, open_data

PROJDEF = (
    "+proj=stere +lat_0=90 +lon_0=10 +lat_ts=60 +a=6378137 +b=6356752.3142451802 "
    "+x_0=0 +y_0=0 +no_defs"
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("OR_ABI-L1b-RadF-M6C13_G19_s20263041200.nc", "goes"),
        ("OR_ABI-L2-CMIPF-M6C13_G19_s20263041200.nc", "goes"),
        ("MSG4-SEVI-MSG15-0100-NA-20261031221244.nat", "seviri"),
        ("MSG4-SEVI-MSG15-0100-NA-20261031221244.zip", "seviri"),
        ("raa01-yw_10000-2611011130-dwd---bin.hdf5", "radolan"),
        ("3B-DAY.MS.MRG.3IMERG.20260101.V07B.nc4", "netcdf"),
        ("3B-HHR-L.MS.MRG.3IMERG.20260101-S000000.HDF5", "hdf5"),
        ("icon_2026110300_000.grib2", "grib"),
        ("era5.grb", "grib"),
        ("scene.TIF", "geotiff"),
        ("store.zarr", "zarr"),
        ("stundenwerte_TU_00044_akt.zip", None),
        ("notes.txt", None),
    ],
)
def test_detect_format(name, expected):
    assert detect_format(name) == expected


def test_unknown_format_has_clear_error(tmp_path):
    path = tmp_path / "data.xyz"
    path.write_bytes(b"1")
    with pytest.raises(NoReaderError, match="Supported"):
        open_data(path)
    with pytest.raises(NoReaderError, match="Unknown format"):
        readers.reader_for("nope")


def test_every_listed_format_has_a_reader_function():
    for name in readers.FORMATS:
        assert callable(readers.reader_for(name))


def test_netcdf_roundtrip(tmp_path):
    xr = pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    path = tmp_path / "a.nc"
    xr.Dataset({"t": (("y", "x"), [[1.0, 2.0], [3.0, 4.0]])}).to_netcdf(path)
    dataset = open_data(path)
    assert dataset["t"].shape == (2, 2)
    assert "t" in readers.summarize(dataset)


def test_zarr_roundtrip(tmp_path):
    xr = pytest.importorskip("xarray")
    pytest.importorskip("zarr")
    path = tmp_path / "a.zarr"
    xr.Dataset({"t": (("y",), [1.0, 2.0, 3.0])}).to_zarr(path)
    assert open_data(path)["t"].shape == (3,)


def test_geotiff_roundtrip(tmp_path):
    xr = pytest.importorskip("xarray")
    rioxarray = pytest.importorskip("rioxarray")
    del rioxarray
    path = tmp_path / "a.tif"
    array = xr.DataArray(
        [[[1.0, 2.0], [3.0, 4.0]]],
        dims=("band", "y", "x"),
        coords={"band": [1], "y": [1.5, 0.5], "x": [0.5, 1.5]},
    ).rio.write_crs("EPSG:4326")
    array.rio.to_raster(path)
    dataset = open_data(path)
    assert dataset["data"].shape == (1, 2, 2)
    assert "crs_wkt" in dataset.attrs


def test_plain_hdf5_with_group(tmp_path):
    h5py = pytest.importorskip("h5py")
    pytest.importorskip("h5netcdf")
    path = tmp_path / "imerg_like.HDF5"
    with h5py.File(path, "w") as handle:
        handle.create_group("Grid").create_dataset("precipitation", data=[[1.0, 2.0, 3.0]] * 2)
    dataset = open_data(path)
    assert "precipitation" in dataset
    assert dataset["precipitation"].shape == (2, 3)


def test_hdf5_nested_groups_skip_metadata(tmp_path):
    h5py = pytest.importorskip("h5py")
    pytest.importorskip("h5netcdf")
    from eo_fetch.readers.generic import first_data_group

    path = tmp_path / "nested.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("Metadata/Extent/box", data=[[1.0, 2.0], [3.0, 4.0]])
        handle.create_dataset("HDFEOS/GRIDS/NO2/Data Fields/column", data=[[1.0, 2.0, 3.0]] * 2)
    assert first_data_group(path) == "HDFEOS/GRIDS/NO2/Data Fields"
    dataset = open_data(path)
    assert "column" in dataset
    assert dataset["column"].shape == (2, 3)


def write_odim(path, raw):
    h5py = pytest.importorskip("h5py")
    with h5py.File(path, "w") as handle:
        handle.create_group("what").attrs.update({"date": "20261101", "time": "113000"})
        where = handle.create_group("where")
        where.attrs.update(
            {
                "projdef": PROJDEF,
                "xsize": raw.shape[1],
                "ysize": raw.shape[0],
                "xscale": 1000.0,
                "yscale": 1000.0,
                "LL_lon": 9.0,
                "LL_lat": 50.0,
            }
        )
        data = handle.create_group("dataset1/data1")
        data.create_dataset("data", data=raw)
        what = data.create_group("what")
        what.attrs.update(
            {
                "quantity": "RATE",
                "gain": 0.5,
                "offset": 0.0,
                "nodata": 65535,
                "undetect": 0,
            }
        )


def test_radolan_odim(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("pyproj")
    pytest.importorskip("xarray")
    raw = np.array([[0, 2, 4], [6, 65535, 8]], dtype="uint16")
    path = tmp_path / "raa01-yw_10000-2611011130-dwd---bin.hdf5"
    write_odim(path, raw)
    dataset = open_data(path)
    rate = dataset["rate"]
    assert rate.dims == ("y", "x")
    assert rate.attrs["units"] == "mm/h"
    assert rate.values[0, 0] == 0.0  # undetect
    assert rate.values[0, 1] == 1.0  # 2 * gain
    assert np.isnan(rate.values[1, 1])  # nodata
    assert dataset["y"].values[0] > dataset["y"].values[-1]  # north first
    assert dataset["x"].values[0] < dataset["x"].values[-1]
    assert dataset["time"].values == np.datetime64(datetime(2026, 11, 1, 11, 30))
    assert "crs_wkt" in dataset.attrs


def test_regrid_radolan_like(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("pyproj")
    pytest.importorskip("pyresample")
    pytest.importorskip("xarray")
    from eo_fetch.regrid import to_latlon

    raw = np.full((40, 40), 10, dtype="uint16")
    path = tmp_path / "raa01-yw_10000-2611011130-dwd---bin.hdf5"
    write_odim(path, raw)
    dataset = open_data(path)
    result = to_latlon(dataset, resolution=0.05)
    assert set(result.dims) == {"lat", "lon"}
    assert float(result["rate"].max()) == 5.0
    assert result["lat"].values[0] > result["lat"].values[-1]
    assert 8.5 < float(result["lon"].min()) < 10.5
    assert 49.5 < float(result["lat"].min()) < 51.0


def test_goes_and_seviri_helpers():
    from eo_fetch.readers.satellite import goes_channel, goes_reader

    assert goes_channel("OR_ABI-L2-CMIPC-M6C05_G18_s1_e2_c3.nc") == "C05"
    assert goes_channel("OR_ABI-L1b-RadC-M3C13_G19_s1.nc") == "C13"
    assert goes_channel("OR_ABI-L2-MCMIPC-M6_G18_s1.nc") is None
    assert goes_reader("OR_ABI-L1b-RadF-M6C13_G19_s1.nc") == "abi_l1b"
    assert goes_reader("OR_ABI-L2-CMIPF-M6C13_G19_s1.nc") == "abi_l2_nc"
    with pytest.raises(ValueError, match="not a recognised"):
        goes_reader("other.nc")


def test_seviri_nat_extraction_from_zip(tmp_path):
    import zipfile

    from eo_fetch.readers.satellite import extract_native

    archive = tmp_path / "MSG4-test.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("MSG4-test.nat", b"x")
        zf.writestr("manifest.xml", b"<x/>")
    work = tmp_path / "work"
    work.mkdir()
    assert extract_native(archive, work).name == "MSG4-test.nat"
    nat = tmp_path / "plain.nat"
    nat.write_bytes(b"x")
    assert extract_native(nat, work) == nat


def test_grib_needs_earthkit_message(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("earthkit"):
            raise ImportError("no earthkit")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    path = tmp_path / "a.grib2"
    path.write_bytes(b"GRIB")
    with pytest.raises(RuntimeError, match="earthkit"):
        open_data(path)


def test_check_product_with_fake_backend(tmp_path):
    pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    import xarray as xr

    from eo_fetch import checkreaders
    from eo_fetch.models import Item
    from eo_fetch.providers import ProviderInfo

    source = tmp_path / "src.nc"
    xr.Dataset({"t": (("x",), [1.0, 2.0])}).to_netcdf(source)
    data = source.read_bytes()

    class FakeBackend:
        max_connections = 1

        def search(self, query):
            return [
                Item("p", "prod", "big.nc", size=10**9),
                Item("p", "prod", "small.nc", size=len(data)),
            ]

        def fetch(self, item, target):
            target.write_bytes(data)

    info = ProviderInfo(name="p", backend="local", title="t", products={"a": "prod"})
    row = checkreaders.check_product(info, "a", FakeBackend(), tmp_path / "out", 3, 100.0)
    assert row.status == "ok"
    assert row.format == "netcdf"
    assert "small.nc" in row.detail

    class OnlyUnknown(FakeBackend):
        def search(self, query):
            return [Item("p", "prod", "x.bin", size=5)]

        def fetch(self, item, target):
            target.write_bytes(b"hello")

    row = checkreaders.check_product(info, "a", OnlyUnknown(), tmp_path / "out2", 3, 100.0)
    assert row.status == "no reader"
