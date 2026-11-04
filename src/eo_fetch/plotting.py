"""Plot any dataset eo-fetch can open on a map, in the common style registry (earthkit-plots)."""

from __future__ import annotations

from pathlib import Path

from eo_fetch import styles

LAT_NAMES = ("lat", "latitude")
LON_NAMES = ("lon", "longitude")


def find_dim(dims, names) -> str | None:
    for name in dims:
        if str(name).lower() in names:
            return name
    return None


def choose_variable(dataset, variable: str | None = None) -> str:
    """The variable to draw: the one asked for, else the first with at least two dimensions."""
    if variable:
        if variable not in dataset.data_vars:
            available = ", ".join(dataset.data_vars)
            raise ValueError(f"No variable {variable!r}. Available: {available}")
        return variable
    candidates = [
        name
        for name, array in dataset.data_vars.items()
        if array.ndim >= 2 and not is_auxiliary(dataset, name)
    ]
    for name in candidates:
        dims = {str(d).lower() for d in dataset[name].dims}
        if dims & set(LAT_NAMES) and dims & set(LON_NAMES):
            return name
        if {"y", "x"} <= dims:
            return name
    if candidates:
        return candidates[0]
    raise ValueError(f"No variable with two or more dimensions in {list(dataset.data_vars)}")


BOUNDS_WORDS = ("bnds", "bounds", "vertices")


def is_auxiliary(dataset, name: str) -> bool:
    """True for cell-bounds variables (``lat_bnds``, ``time_bnds``, ...), which are not data."""
    lowered = name.lower()
    if any(word in lowered for word in BOUNDS_WORDS):
        return True
    if any(any(word in str(d).lower() for word in BOUNDS_WORDS) for d in dataset[name].dims):
        return True
    referenced = {
        variable.attrs["bounds"]
        for variable in (*dataset.data_vars.values(), *dataset.coords.values())
        if "bounds" in variable.attrs
    }
    return name in referenced


def prepare(dataset, variable: str | None = None, resolution: float | None = None, bbox=None):
    """Return a 2-D DataArray on a latitude/longitude grid, ready to plot.

    Projected data (dimensions y, x with ``crs_wkt`` in the attributes) is regridded first.
    Extra dimensions (time, band, level) are reduced to their first entry. ``bbox`` is
    (west, south, east, north) in degrees.
    """
    name = choose_variable(dataset, variable)
    subset = dataset[[name]]
    subset.attrs = dict(dataset.attrs)
    dims = subset[name].dims
    lat = find_dim(dims, LAT_NAMES)
    lon = find_dim(dims, LON_NAMES)
    if lat is None or lon is None:
        if not ({"y", "x"} <= set(dims) and "crs_wkt" in dataset.attrs):
            raise ValueError(
                f"{name} has dimensions {tuple(dims)}: not on a regular latitude/longitude "
                "or projected (y, x) grid, so it cannot be drawn yet"
            )
        from pyproj import CRS

        from eo_fetch.regrid import crop_projected, decimate, projected_bounds, to_latlon

        extra = [d for d in dims if d not in ("y", "x")]
        subset = subset.isel({d: 0 for d in extra})
        if CRS.from_wkt(dataset.attrs["crs_wkt"]).is_geographic:
            subset = subset.rename({"y": "lat", "x": "lon"})
        else:
            if bbox:
                subset = crop_projected(subset, bbox)
            subset = decimate(subset)
            if resolution is None:
                step = abs(float(subset["x"][1] - subset["x"][0]))
                resolution = max(step / 111_000.0, 0.0001)
            subset = to_latlon(subset, resolution=resolution, bbox=bbox or projected_bounds(subset))
        lat, lon = "lat", "lon"
    array = subset[name]
    extra = [d for d in array.dims if d not in (lat, lon)]
    array = array.isel({d: 0 for d in extra})
    array = array.rename({lat: "latitude", lon: "longitude"})
    if float(array["longitude"].max()) > 180.0:  # 0..360 grids (ECMWF, NCEP): wrap to -180..180
        wrapped = ((array["longitude"] + 180.0) % 360.0) - 180.0
        array = array.assign_coords(longitude=wrapped).sortby("longitude")
    if bbox:
        west, south, east, north = bbox
        lats = array["latitude"].values
        lat_slice = slice(north, south) if lats[0] > lats[-1] else slice(south, north)
        array = array.sel(latitude=lat_slice, longitude=slice(west, east))
    array.name = name
    # The data is on a plain lat/lon grid now: drop links to projection variables that no longer
    # exist, and coordinates other than the grid and the time.
    array.attrs = {k: v for k, v in array.attrs.items() if k not in ("grid_mapping", "coordinates")}
    array.encoding.pop("grid_mapping", None)
    stray = [c for c in array.coords if c not in array.dims and c != "time"]
    return array.drop_vars(stray)


def default_title(array) -> str:
    """A title from the variable's long name (or name) and its time, when it has one."""
    label = str(array.attrs.get("long_name") or array.name)
    if "time" in array.coords and array["time"].size == 1:
        import numpy as np

        moment = array["time"].values.ravel()[0]
        if isinstance(moment, np.datetime64):
            stamp = np.datetime_as_string(moment, unit="m").replace("T", " ")
        elif hasattr(moment, "strftime"):  # cftime objects of model calendars (noleap, ...)
            stamp = moment.strftime("%Y-%m-%d %H:%M")
        else:
            stamp = str(moment)
        return f"{label}, {stamp} UTC"
    return label


def plot(
    source,
    output: Path,
    variable: str | None = None,
    style: str | None = None,
    domain=None,
    resolution: float | None = None,
    bbox=None,
    title: str | None = None,
    **options,
) -> str:
    """Draw ``source`` (a file path or an xarray Dataset) to ``output``; return the style used.

    ``domain`` is an earthkit-plots domain name such as ``"Europe"``; with ``bbox`` and no
    ``domain`` the map is limited to the box. ``options`` go to the file reader.
    """
    try:
        import earthkit.plots as ekp
    except ImportError as error:
        raise RuntimeError(
            "Plotting needs earthkit-plots: pip install 'eo-fetch[earthkit]'"
        ) from error
    from eo_fetch.readers import open_data

    opened = isinstance(source, str | Path)
    dataset = open_data(source, **options) if opened else source
    try:
        array = prepare(dataset, variable, resolution, bbox)
        chosen = styles.get_style(style) if style else styles.pick_style(array.name, array.attrs)
        kwargs = {}
        if chosen is not None:
            kwargs["style"] = styles.to_earthkit(chosen)
        if domain is None and bbox:
            west, south, east, north = bbox
            domain = [west, east, south, north]
        label = title or default_title(array)
        # The time is in the title; earthkit would convert the coordinate to a timestamp, which
        # fails on Windows for dates before 1970 (model runs start in 1850).
        array = array.drop_vars("time", errors="ignore")
        chart = ekp.quickplot(array, domain=domain, subplot_titles=label, **kwargs)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        chart.save(str(output))
    finally:
        if opened:  # the data may be read lazily, so close only after the picture is saved
            dataset.close()
    return chosen.name if chosen else "default"
