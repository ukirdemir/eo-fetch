import pytest

from eo_fetch import styles


def test_pick_style_by_name_and_units():
    pick = styles.pick_style
    assert pick("IR_108", {"units": "K"}).name == "ir-brightness"
    assert pick("C13", {"units": "K"}).name == "ir-brightness"
    assert pick("WV_062", {"units": "K"}).name == "wv-brightness"
    assert pick("rate", {"units": "mm/h", "quantity": "RATE"}).name == "precip-rate"
    assert pick("C04", {"units": "%", "long_name": "reflectance factor"}).name == "reflectance"
    assert pick("C04", {"units": "1", "long_name": "reflectance factor"}).name == (
        "reflectance-fraction"
    )
    assert pick("cloud_mask", {}).name == "cloud-mask"
    assert pick("cloud_top_height", {"units": "m"}).name == "cloud-top-height"
    assert pick("t2m", {"units": "K"}).name == "temperature-k"
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
