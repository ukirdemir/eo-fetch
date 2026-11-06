"""Hand data over to other libraries: earthkit-data objects and NetCDF/Zarr files."""

from __future__ import annotations

from pathlib import Path


def to_xarray(source, **options):
    """Open a file (or pass through a Dataset) as an ``xarray.Dataset``."""
    from eo_fetch.readers import open_data

    return open_data(source, **options) if isinstance(source, str | Path) else source


def to_latlon_dataset(dataset, resolution: float, bbox=None):
    """Regrid every projected (y, x) variable of a dataset to lat/lon; lat/lon data is kept."""
    if "crs_wkt" in dataset.attrs and {"y", "x"} <= set(dataset.dims):
        from eo_fetch.regrid import to_latlon

        return to_latlon(dataset, resolution=resolution, bbox=bbox)
    return dataset


def to_earthkit(source, variable: str | None = None, resolution=None, bbox=None, **options):
    """An earthkit-data object for a file, ready for earthkit-plots, -regrid or -transforms.

    Projected data is regridded to lat/lon first (see ``resolution`` and ``bbox``).
    """
    try:
        import earthkit.data as ekd
    except ImportError as error:
        raise RuntimeError("This needs earthkit-data: pip install earthkit-data") from error
    from eo_fetch.plotting import prepare

    array = prepare(to_xarray(source, **options), variable, resolution, bbox)
    return ekd.from_object(array)


def convert(source, output: Path, resolution: float | None = None, bbox=None, **options) -> Path:
    """Write a readable file as NetCDF (``.nc``) or Zarr (``.zarr``), optionally on lat/lon."""
    dataset = to_xarray(source, **options)
    if resolution:
        dataset = to_latlon_dataset(dataset, resolution, bbox)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.lower()
    if suffix == ".zarr":
        dataset.to_zarr(output, mode="w")
    elif suffix in (".nc", ".nc4"):
        dataset.to_netcdf(output)
    else:
        raise ValueError(f"Output must end in .nc or .zarr, not {output.suffix!r}")
    return output
