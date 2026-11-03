"""Resample projected data (radar, geostationary x/y grids) to a latitude/longitude grid."""

from __future__ import annotations


def projected_bounds(dataset) -> tuple[float, float, float, float]:
    """West, south, east, north in degrees covered by a dataset with projected x, y."""
    import numpy as np
    from pyproj import CRS, Transformer

    crs = CRS.from_wkt(dataset.attrs["crs_wkt"])
    to_geographic = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    step_x = max(1, dataset.sizes["x"] // 50)
    step_y = max(1, dataset.sizes["y"] // 50)
    xx, yy = np.meshgrid(dataset["x"].values[::step_x], dataset["y"].values[::step_y])
    lon, lat = to_geographic.transform(xx, yy)
    ok = np.isfinite(lon) & np.isfinite(lat)
    return float(lon[ok].min()), float(lat[ok].min()), float(lon[ok].max()), float(lat[ok].max())


def crop_projected(dataset, bbox):
    """Cut a projected dataset down to the cells that may fall inside (west, south, east, north).

    Raises ValueError when the box does not touch the data.
    """
    import numpy as np
    from pyproj import CRS, Transformer

    west, south, east, north = bbox
    to_projected = Transformer.from_crs("EPSG:4326", CRS.from_wkt(dataset.attrs["crs_wkt"]), True)
    lons = np.linspace(west, east, 9)
    lats = np.linspace(south, north, 9)
    edge_lon = np.concatenate([lons, lons, np.full(9, west), np.full(9, east)])
    edge_lat = np.concatenate([np.full(9, south), np.full(9, north), lats, lats])
    px, py = to_projected.transform(edge_lon, edge_lat)
    ok = np.isfinite(px) & np.isfinite(py)
    if not ok.any():
        raise ValueError("The bounding box lies outside the area the data covers")
    x, y = dataset["x"].values, dataset["y"].values
    cols = np.where((x >= px[ok].min()) & (x <= px[ok].max()))[0]
    rows = np.where((y >= py[ok].min()) & (y <= py[ok].max()))[0]
    if cols.size == 0 or rows.size == 0:
        raise ValueError("The bounding box lies outside the area the data covers")
    return dataset.isel(
        x=slice(int(cols.min()), int(cols.max()) + 1),
        y=slice(int(rows.min()), int(rows.max()) + 1),
    )


def decimate(dataset, max_pixels: int = 4000):
    """Keep every n-th cell so that neither side exceeds ``max_pixels`` (for plotting)."""
    step = -(-max(dataset.sizes["x"], dataset.sizes["y"]) // max_pixels)
    if step <= 1:
        return dataset
    return dataset.isel(x=slice(None, None, step), y=slice(None, None, step))


def to_latlon(dataset, resolution: float, bbox=None, radius_m: float | None = None):
    """Nearest-neighbour resampling of every (y, x) variable to a regular lat/lon grid.

    ``resolution`` is in degrees, ``bbox`` = (west, south, east, north) defaults to the area the
    data covers. Cells farther than ``radius_m`` (default twice the source cell size) from a source
    cell are NaN. Needs ``dataset.attrs["crs_wkt"]``; y may run north to south or the reverse.
    """
    import numpy as np
    import xarray as xr
    from pyproj import CRS
    from pyresample import create_area_def
    from pyresample.geometry import AreaDefinition
    from pyresample.kd_tree import resample_nearest

    x = dataset["x"].values
    y = dataset["y"].values
    flip_x = bool(x[0] > x[-1])  # scan order east to west: put west first
    if flip_x:
        x = x[::-1]
    dx = abs(float(x[1] - x[0]))
    dy = abs(float(y[1] - y[0]))
    source = AreaDefinition(
        "source",
        "source",
        "source",
        CRS.from_wkt(dataset.attrs["crs_wkt"]),
        len(x),
        len(y),
        (
            float(x.min()) - dx / 2,
            float(y.min()) - dy / 2,
            float(x.max()) + dx / 2,
            float(y.max()) + dy / 2,
        ),
    )
    west, south, east, north = bbox or projected_bounds(dataset)
    target = create_area_def(
        "latlon",
        {"proj": "longlat", "datum": "WGS84"},
        area_extent=(west, south, east, north),
        resolution=float(resolution),
    )
    radius = radius_m or 2 * max(dx, dy)
    flip = bool(y[0] < y[-1])  # pyresample expects the first row to be the northernmost
    variables = {}
    for name, variable in dataset.data_vars.items():
        if variable.dims != ("y", "x"):
            continue
        # integer rasters (Sentinel-2, class maps) need a float array to hold NaN for empty cells
        values = variable.values.astype("float32")
        values = values[::-1] if flip else values
        if flip_x:
            values = values[:, ::-1]
        resampled = resample_nearest(
            source,
            values,
            target,
            radius_of_influence=radius,
            fill_value=np.nan,
        )
        variables[name] = xr.Variable(("lat", "lon"), resampled.astype("float32"), variable.attrs)
    lons, lats = target.get_lonlats()
    result = xr.Dataset(
        variables, coords={"lat": lats[:, 0], "lon": lons[0, :]}, attrs={"crs": "EPSG:4326"}
    )
    if "time" in dataset.coords:
        result = result.assign_coords(time=dataset["time"])
    return result
