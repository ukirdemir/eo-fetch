"""DWD radar composites in ODIM HDF5 (RADOLAN YW, RV, RW and similar) as xarray datasets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

UNITS = {"RATE": "mm/h", "ACRR": "mm", "DBZH": "dBZ"}


def text(value) -> str:
    """Return an HDF5 attribute as str (attributes come as bytes, numpy bytes or str)."""
    if hasattr(value, "decode"):
        return value.decode()
    if hasattr(value, "item") and not isinstance(value, str):
        value = value.item()
        if hasattr(value, "decode"):
            return value.decode()
    return str(value)


def product_time(what) -> datetime | None:
    """The nominal time from the ``what`` group's date (YYYYMMDD) and time (HHMMSS)."""
    if "date" not in what or "time" not in what:
        return None
    stamp = text(what["date"]) + text(what["time"])
    return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def decode(raw, gain: float, offset: float, nodata, undetect):
    """Scale stored integers to physical values; nodata becomes NaN and undetect becomes 0."""
    import numpy as np

    values = raw.astype("float32") * np.float32(gain) + np.float32(offset)
    if undetect is not None:
        values = np.where(raw == undetect, np.float32(0.0), values)
    if nodata is not None:
        values = np.where(raw == nodata, np.float32(np.nan), values)
    return values.astype("float32")


def grid_coordinates(where) -> tuple:
    """Projected cell-centre coordinates x (west to east) and y (north to south).

    The lower-left corner given in ``where`` (LL_lon, LL_lat) is taken as the outer corner of the
    lower-left cell, as in the ODIM specification.
    """
    import numpy as np
    from pyproj import CRS, Transformer

    crs = CRS.from_proj4(text(where["projdef"]))
    to_projected = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x_ll, y_ll = to_projected.transform(float(where["LL_lon"]), float(where["LL_lat"]))
    width, height = int(where["xsize"]), int(where["ysize"])
    dx, dy = float(where["xscale"]), float(where["yscale"])
    x = x_ll + (np.arange(width) + 0.5) * dx
    y = y_ll + (height - np.arange(height) - 0.5) * dy
    return crs, x, y


def open_radolan(path: Path, **options):
    """Open an ODIM HDF5 radar composite.

    Returns a dataset with one variable per stored quantity (for example ``rate``), dimensions
    (y, x) in the product's projection, a scalar ``time`` and the projection as ``crs_wkt`` in
    the attributes. Use ``eo_fetch.regrid.to_latlon`` for a latitude/longitude grid.
    """
    import h5py
    import xarray as xr

    with h5py.File(path, "r") as handle:
        where = handle["where"].attrs
        crs, x, y = grid_coordinates(where)
        variables = {}
        for group_name in sorted(key for key in handle if key.startswith("dataset")):
            for data_name in sorted(key for key in handle[group_name] if key.startswith("data")):
                node = handle[group_name][data_name]
                what = node["what"].attrs
                quantity = text(what["quantity"]) if "quantity" in what else data_name
                values = decode(
                    node["data"][...],
                    float(what.get("gain", 1.0)),
                    float(what.get("offset", 0.0)),
                    what.get("nodata"),
                    what.get("undetect"),
                )
                name = quantity.lower()
                if name in variables:
                    name = f"{name}_{group_name}_{data_name}"
                variables[name] = xr.Variable(
                    ("y", "x"), values, {"units": UNITS.get(quantity, ""), "quantity": quantity}
                )
        if not variables:
            raise ValueError(f"No dataset*/data*/data arrays found in {path.name}")
        time = product_time(handle["what"].attrs)
    dataset = xr.Dataset(variables, coords={"x": x, "y": y})
    dataset.attrs["crs_wkt"] = crs.to_wkt()
    dataset.attrs["source"] = path.name
    if time is not None:
        dataset = dataset.assign_coords(time=time.replace(tzinfo=None))
    return dataset
