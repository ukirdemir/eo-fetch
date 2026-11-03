"""Open downloaded files as xarray datasets, whatever their format.

``open_data(path)`` picks a reader from the file name and extension. Dedicated readers exist for
SEVIRI, GOES ABI and RADOLAN/ODIM radar composites; NetCDF, HDF5, Zarr, GRIB and GeoTIFF use
the usual libraries. Anything else raises ``NoReaderError`` with the supported formats listed.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

NETCDF_SUFFIXES = (".nc", ".nc4", ".cdf", ".netcdf")
HDF5_SUFFIXES = (".h5", ".hdf5", ".he5", ".hdf")
GRIB_SUFFIXES = (".grib", ".grb", ".grib2", ".grb2", ".grib1", ".grb1")
TIFF_SUFFIXES = (".tif", ".tiff", ".asc", ".jp2")  # any GDAL raster (COG, ASCII grid, JPEG 2000)
SEVIRI_L2 = re.compile(r"-sevi-msg(?:clmk|clth|aese|crmn|firg|mpeg|ocae)-")


class NoReaderError(RuntimeError):
    """The file format has no reader (yet) or cannot be recognised."""


def detect_format(path: str | Path) -> str | None:
    """Name the format of a file from its name, or None if it is not recognised.

    Dedicated names win over extensions: ``OR_ABI-...nc`` is GOES, ``MSG...nat`` or ``MSG...zip``
    is SEVIRI native, ``raa0...hdf5`` is a DWD radar composite.
    """
    path = Path(path)
    name = path.name.lower()
    if name.endswith(".zarr"):
        return "zarr"
    if name.startswith("or_abi-") and name.endswith(NETCDF_SUFFIXES):
        return "goes"
    if "fci-1c-rrad" in name and name.endswith(NETCDF_SUFFIXES):
        return "fci"
    if SEVIRI_L2.search(name) and name.endswith(".grb"):
        return "seviri-l2"
    if name.startswith("msg") and name.endswith((".nat", ".zip")):
        return "seviri"
    if name.startswith("raa0") and name.endswith(HDF5_SUFFIXES):
        return "radolan"
    if name.endswith(NETCDF_SUFFIXES):
        return "netcdf"
    if name.endswith(HDF5_SUFFIXES):
        return "hdf5"
    if name.endswith(GRIB_SUFFIXES):
        return "grib"
    if name.endswith(TIFF_SUFFIXES):
        return "geotiff"
    return None


def reader_for(format_name: str) -> Callable:
    """Return the reader function of a format (imports its libraries only now)."""
    if format_name in {"netcdf", "hdf5", "zarr", "grib", "geotiff"}:
        from eo_fetch.readers import generic

        return getattr(generic, f"open_{format_name}")
    if format_name == "radolan":
        from eo_fetch.readers import radolan

        return radolan.open_radolan
    if format_name in {"seviri", "goes", "seviri-l2", "fci"}:
        from eo_fetch.readers import satellite

        return getattr(satellite, f"open_{format_name.replace('-', '_')}")
    raise NoReaderError(f"Unknown format {format_name!r}. Available: {', '.join(FORMATS)}")


FORMATS = (
    "netcdf",
    "hdf5",
    "zarr",
    "grib",
    "geotiff",
    "radolan",
    "seviri",
    "seviri-l2",
    "fci",
    "goes",
)


def open_data(path: str | Path, format: str | None = None, **options):
    """Open a file as an ``xarray.Dataset``.

    ``format`` overrides detection. ``options`` go to the reader (for example ``channels``,
    ``resolution`` and ``area_extent`` for SEVIRI and GOES, ``group`` for HDF5).
    """
    path = Path(path)
    if format:
        return reader_for(format)(path, **options)
    found = resolve(path)
    if not found:
        raise NoReaderError(
            f"No reader for {path.name}: format not recognised"
            f"{describe_container(path)}. Supported: {', '.join(FORMATS)}. "
            "Pass format=... if you know it."
        )
    formats = {name for name, _ in found}
    if len(found) == 1:
        name, target = found[0]
        return reader_for(name)(target, **options)
    if formats == {"netcdf"}:
        import xarray as xr

        options.setdefault("data_vars", "all")
        try:
            return xr.open_mfdataset([str(p) for _, p in found], combine="by_coords", **options)
        except Exception as error:
            raise NoReaderError(
                f"{path.name} holds {len(found)} NetCDF files that do not combine by "
                f"coordinates ({type(error).__name__}); open them one by one."
            ) from error
    listing = ", ".join(p.name for _, p in found[:5])
    raise NoReaderError(f"{path.name} holds several files ({listing}, ...); open one of them.")


def describe_container(path: Path) -> str:
    """For a zip that holds nothing readable, say what is inside."""
    from eo_fetch.readers import unpack

    if unpack.sniff(path) == "zip":
        names = unpack.zip_members(path)
        return f" (zip containing {', '.join(names[:4])}{', ...' if len(names) > 4 else ''})"
    return ""


def resolve(path: Path, depth: int = 0) -> list[tuple[str, Path]]:
    """Find what to read: a list of (format, file), unpacking gzip, bzip2 and zip containers.

    The name decides first (dedicated names such as GOES or SEVIRI win); the first bytes decide
    for files without a usable name. A zip that holds a SEVIRI ``.nat`` is read as SEVIRI.
    """
    from eo_fetch.readers import unpack

    path = Path(path)
    if path.is_dir():
        return [("zarr", path)] if path.name.lower().endswith(".zarr") else []
    kind = unpack.sniff(path)
    if kind in {"gzip", "bzip2"} and depth < 3:
        return resolve(unpack.unpack_compressed(path, kind), depth + 1)
    if kind == "zip" and depth < 3:
        names = unpack.zip_members(path)
        if any(
            member.rsplit("/", 1)[-1].lower().startswith("msg") and member.lower().endswith(".nat")
            for member in names
        ):
            return [("seviri", path)]
        if any("fci-1c-rrad" in member.lower() for member in names):
            return [("fci", path)]
        found: list[tuple[str, Path]] = []
        for member in unpack.unpack_zip(path):
            found += resolve(member, depth + 1)
        return found
    name_format = detect_format(path)
    if name_format:
        return [(name_format, path)]
    sniffed = {"hdf5": "hdf5", "netcdf": "netcdf", "grib": "grib", "geotiff": "geotiff"}
    if kind in sniffed:
        return [(sniffed[kind], path)]
    return []


def summarize(dataset) -> str:
    """A short text description of a dataset: dimensions, variables, time range."""
    lines = [f"dims: {dict(dataset.sizes)}"]
    for name, variable in dataset.data_vars.items():
        units = variable.attrs.get("units", "")
        lines.append(f"  {name}: {tuple(variable.dims)} {variable.dtype} {units}".rstrip())
    if "time" in dataset.coords and dataset["time"].size:
        times = dataset["time"].values.ravel()
        lines.append(f"time: {times.min()} .. {times.max()}")
    return "\n".join(lines)


__all__ = [
    "FORMATS",
    "NoReaderError",
    "detect_format",
    "open_data",
    "reader_for",
    "resolve",
    "summarize",
]
