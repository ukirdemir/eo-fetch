import pytest

from eo_fetch import bridge


def small_dataset():
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    return xr.Dataset(
        {"t2m": (("lat", "lon"), np.arange(12.0).reshape(3, 4), {"units": "K"})},
        coords={"lat": [2.0, 1.0, 0.0], "lon": [0.0, 1.0, 2.0, 3.0]},
    )


def test_convert_netcdf_and_zarr(tmp_path):
    pytest.importorskip("netCDF4")
    pytest.importorskip("zarr")
    import xarray as xr

    source = tmp_path / "in.nc"
    small_dataset().to_netcdf(source)
    nc = bridge.convert(source, tmp_path / "out" / "a.nc")
    assert xr.open_dataset(nc)["t2m"].shape == (3, 4)
    zarr_path = bridge.convert(source, tmp_path / "b.zarr")
    assert xr.open_zarr(zarr_path)["t2m"].shape == (3, 4)


def test_convert_rejects_unknown_output(tmp_path):
    pytest.importorskip("netCDF4")
    source = tmp_path / "in.nc"
    small_dataset().to_netcdf(source)
    with pytest.raises(ValueError, match=r"\.nc or \.zarr"):
        bridge.convert(source, tmp_path / "out.csv")


def test_lat_lon_data_is_left_alone():
    dataset = small_dataset()
    assert bridge.to_latlon_dataset(dataset, 0.5) is dataset


def test_to_earthkit(tmp_path):
    pytest.importorskip("earthkit.data")
    pytest.importorskip("netCDF4")
    source = tmp_path / "in.nc"
    small_dataset().to_netcdf(source)
    assert bridge.to_earthkit(source) is not None
