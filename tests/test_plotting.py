import pytest

from eo_fetch import styles


def test_pick_style_by_name_and_units():
    pick = styles.pick_style
    assert pick("IR_108", {"units": "K"}).name == "ir-brightness"
    assert pick("C13", {"units": "K"}).name == "ir-brightness"
    assert pick("WV_062", {"units": "K"}).name == "wv-brightness"
    assert pick("rate", {"units": "mm/h", "quantity": "RATE"}).name == "precip-rate"
    assert pick("precipitation", {"units": "mm/day"}).name == "precip-daily"
    assert pick("precipitation_cnt", {"units": "count"}) is None
    assert pick("C04", {"units": "%", "long_name": "reflectance factor"}).name == "reflectance"
    assert pick("C04", {"units": "1", "long_name": "reflectance factor"}).name == (
        "reflectance-fraction"
    )
    assert pick("cloud_mask", {}).name == "cloud-mask"
    assert pick("cloud_top_height", {"units": "m"}).name == "cloud-top-height"
    assert pick("t2m", {"units": "K"}).name == "temperature-k"
    assert pick("2t", {"units": "K"}).name == "temperature-k"
    grib = {"units": "K", "standard_name": "air_temperature", "long_name": "2 metre temperature"}
    assert pick("2t", grib).name == "temperature-k"  # "air_" must not look like "ir_"
    assert pick("terrain_height", {"units": "mm/h"}) is None  # "rain" inside "terrain"
    assert pick("msl", {"units": "Pa"}).name == "pressure"
    assert pick("t2m", {"units": "degC"}).name == "temperature-c"
    assert pick("SIS", {"units": "W m-2"}).name == "radiation"
    assert pick("something_else", {"units": "furlongs"}) is None


def test_every_style_is_complete():
    for name, style in styles.STYLES.items():
        assert style.name == name
        assert style.description
        if style.categories:
            assert len(style.levels) == len(style.categories) + 1
            assert len(style.colors) == len(style.categories)
        else:
            assert list(style.levels) == sorted(style.levels)


def test_get_style_unknown():
    with pytest.raises(KeyError, match="Available"):
        styles.get_style("nope")


def test_to_earthkit_builds_style():
    pytest.importorskip("earthkit.plots")
    for style in styles.STYLES.values():
        assert styles.to_earthkit(style) is not None


def test_prepare_lat_lon_with_extra_dimension_and_bbox():
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    from eo_fetch.plotting import prepare

    lat = np.arange(60.0, 40.0, -1.0)
    lon = np.arange(0.0, 20.0, 1.0)
    data = xr.Dataset(
        {"t2m": (("time", "lat", "lon"), np.zeros((2, 20, 20)), {"units": "K"})},
        coords={"time": [0, 1], "lat": lat, "lon": lon},
    )
    array = prepare(data, bbox=(5.0, 45.0, 10.0, 50.0))
    assert array.dims == ("latitude", "longitude")
    assert float(array["longitude"].min()) == 5.0
    assert float(array["longitude"].max()) == 10.0
    assert float(array["latitude"].max()) == 50.0
    assert array.attrs["units"] == "K"


def test_prepare_wraps_0_360_longitudes():
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    from eo_fetch.plotting import prepare

    lon = np.arange(0.0, 360.0, 10.0)
    data = xr.Dataset(
        {"2t": (("latitude", "longitude"), np.tile(lon, (3, 1)), {"units": "K"})},
        coords={"latitude": [10.0, 0.0, -10.0], "longitude": lon},
    )
    array = prepare(data, bbox=(-20.0, -10.0, 30.0, 10.0))
    assert float(array["longitude"].min()) == -20.0
    assert float(array["longitude"].max()) == 30.0
    assert float(array.sel(longitude=-20.0).isel(latitude=0)) == 340.0  # was 340 degrees east


def test_prepare_rejects_unplottable_grids():
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    from eo_fetch.plotting import prepare

    data = xr.Dataset({"v": (("number", "values"), np.zeros((2, 5)))})
    with pytest.raises(ValueError, match="cannot be drawn"):
        prepare(data)


def projected(descending_x: bool):
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    pyproj = pytest.importorskip("pyproj")
    x = 1_000_000.0 + np.arange(40) * 1000.0
    y = 6_000_000.0 - np.arange(40) * 1000.0
    values = np.tile(np.arange(40, dtype="float32"), (40, 1))  # grows eastward
    if descending_x:
        x, values = x[::-1], values[:, ::-1]
    return xr.Dataset(
        {"v": (("y", "x"), values)},
        coords={"x": x, "y": y},
        attrs={"crs_wkt": pyproj.CRS("EPSG:3857").to_wkt()},
    )


def test_crop_projected_and_decimate():
    pytest.importorskip("numpy")
    pytest.importorskip("pyproj")
    from pyproj import Transformer

    from eo_fetch.regrid import crop_projected, decimate

    dataset = projected(False)
    to_geo = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    west, north = to_geo.transform(dataset["x"].values[10], dataset["y"].values[10])
    east, south = to_geo.transform(dataset["x"].values[20], dataset["y"].values[20])
    cropped = crop_projected(dataset, (west, south, east, north))
    assert 10 <= cropped.sizes["x"] <= 13 and 10 <= cropped.sizes["y"] <= 13
    assert float(cropped["x"].min()) >= float(dataset["x"].values[10]) - 1.0
    with pytest.raises(ValueError, match="outside"):
        crop_projected(dataset, (100.0, 0.0, 101.0, 1.0))
    assert decimate(dataset, max_pixels=40) is dataset
    assert decimate(dataset, max_pixels=10).sizes["x"] == 10


def test_prepare_geographic_geotiff_and_projected_raster():
    np = pytest.importorskip("numpy")
    xr = pytest.importorskip("xarray")
    pytest.importorskip("pyproj")
    pytest.importorskip("pyresample")
    from pyproj import CRS

    from eo_fetch.plotting import prepare

    geographic = xr.Dataset(
        {"data": (("band", "y", "x"), np.zeros((1, 4, 5)))},
        coords={"band": [1], "y": [3.5, 2.5, 1.5, 0.5], "x": [0.5, 1.5, 2.5, 3.5, 4.5]},
        attrs={"crs_wkt": CRS.from_epsg(4326).to_wkt()},
    )
    array = prepare(geographic)
    assert array.dims == ("latitude", "longitude")
    raster = projected(False).expand_dims(band=[1])
    array = prepare(raster, resolution=0.01)
    assert array.dims == ("latitude", "longitude")


def test_regrid_integer_raster_keeps_values_and_uses_nan():
    np = pytest.importorskip("numpy")
    pytest.importorskip("pyresample")
    from eo_fetch.regrid import to_latlon

    dataset = projected(False)
    dataset["v"] = dataset["v"].astype("uint16")
    result = to_latlon(dataset, resolution=0.01, bbox=(8.0, 40.0, 20.0, 60.0))
    assert result["v"].dtype == np.float32
    assert np.isnan(result["v"].values).any()  # cells outside the data
    assert float(np.nanmax(result["v"].values)) == 39.0


def test_regrid_is_independent_of_x_scan_direction():
    np = pytest.importorskip("numpy")
    pytest.importorskip("pyresample")
    from eo_fetch.regrid import to_latlon

    east_first = to_latlon(projected(False), resolution=0.01)
    west_first = to_latlon(projected(True), resolution=0.01)
    np.testing.assert_allclose(east_first["v"].values, west_first["v"].values, equal_nan=True)
    row = east_first["v"].values[east_first.sizes["lat"] // 2]
    valid = row[~np.isnan(row)]
    assert valid[0] < valid[-1]  # values grow eastward
