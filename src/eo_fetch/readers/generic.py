"""Readers for common self-describing formats, built on xarray, earthkit-data and rioxarray."""

from __future__ import annotations

from pathlib import Path


def open_netcdf(path: Path, **options):
    """NetCDF (classic or HDF5-based) through xarray."""
    import xarray as xr

    return xr.open_dataset(path, **options)


def first_data_group(path: Path) -> str | None:
    """Name of the first top-level HDF5 group, for files like IMERG that keep data in ``Grid``."""
    import h5py

    with h5py.File(path, "r") as handle:
        groups = [key for key, node in handle.items() if isinstance(node, h5py.Group)]
    return "Grid" if "Grid" in groups else (groups[0] if groups else None)


def open_hdf5(path: Path, group: str | None = None, **options):
    """HDF5 through xarray's h5netcdf engine, reading ``group`` (default: ``Grid`` or the first).

    Plain HDF5 without dimension scales gets generic dimension names (phony_dim_0, ...).
    """
    import xarray as xr

    options.setdefault("engine", "h5netcdf")
    options.setdefault("phony_dims", "sort")
    if group is None:
        try:
            dataset = xr.open_dataset(path, **options)
            if dataset.data_vars:
                return dataset
        except (OSError, ValueError):
            pass
        group = first_data_group(path)
    return xr.open_dataset(path, group=group, **options)


def open_zarr(path: Path, **options):
    """A Zarr store through xarray."""
    import xarray as xr

    return xr.open_zarr(path, **options)


def open_grib(path: Path, **options):
    """GRIB through earthkit-data (ERA5, ECMWF Open Data, ICON, GFS, ...)."""
    try:
        import earthkit.data as ekd
    except ImportError as error:
        raise RuntimeError(
            "Reading GRIB needs earthkit-data: pip install 'eo-fetch[earthkit]'"
        ) from error
    return ekd.from_source("file", str(path)).to_xarray(**options)


def open_geotiff(path: Path, **options):
    """GeoTIFF or COG through rioxarray; bands become the ``band`` dimension of ``data``."""
    import rioxarray

    array = rioxarray.open_rasterio(path, **options)
    return array.to_dataset(name="data")
