"""Geostationary imagery (MSG SEVIRI native, GOES ABI NetCDF) through satpy, as xarray."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

SEVIRI_CHANNELS = ("IR_108", "WV_062")
# A latitude/longitude window that covers most of what a geostationary satellite sees.
DEFAULT_EXTENT = (-80.0, -80.0, 80.0, 80.0)
BRIGHTNESS_RANGE = (100.0, 350.0)


def goes_channel(name: str) -> str | None:
    """The ABI channel in a file name (``...-M6C13_G19...`` gives ``C13``), None for MCMIP."""
    match = re.search(r"-M\dC(\d{2})_", name)
    return f"C{match.group(1)}" if match else None


def goes_reader(name: str) -> str:
    """The satpy reader for a GOES file name: radiances (L1b) or level-2 products."""
    lowered = name.lower()
    if "abi-l1b" in lowered:
        return "abi_l1b"
    if "abi-l2" in lowered:
        return "abi_l2_nc"
    raise ValueError(f"{name} is not a recognised GOES ABI file name")


def extract_native(path: Path, workdir: Path) -> Path:
    """The .nat file for a path that is either the .nat itself or a Data Store zip of it."""
    if path.suffix.lower() == ".nat":
        return path
    with zipfile.ZipFile(path) as archive:
        archive.extractall(workdir)
    found = sorted(workdir.rglob("*.nat"))
    if not found:
        raise FileNotFoundError(f"No .nat file inside {path.name}")
    return found[0]


def load_scene(paths: list[Path], reader: str, channels, resolution, area_extent):
    """Load channels with satpy, optionally resampling to a latitude/longitude grid."""
    from satpy import Scene

    scene = Scene(filenames=[str(p) for p in paths], reader=reader)
    scene.load(list(channels))
    area = scene[channels[0]].attrs["area"]
    crs_wkt = area.crs.to_wkt()
    if resolution:
        from pyresample import create_area_def

        target = create_area_def(
            "latlon",
            {"proj": "longlat", "datum": "WGS84"},
            area_extent=tuple(area_extent or DEFAULT_EXTENT),
            resolution=float(resolution),
        )
        scene = scene.resample(target, resampler="nearest")
        crs_wkt = target.crs.to_wkt()
    dataset = scene.to_xarray_dataset().load()
    for variable in dataset.data_vars.values():
        variable.attrs.pop("area", None)
    if resolution:
        dataset = dataset.rename({"x": "lon", "y": "lat"})
    dataset.attrs = {"crs_wkt": crs_wkt}
    return dataset


def mask_brightness(dataset):
    """Set infrared and water-vapour values outside 100-350 K to NaN (bad calibration)."""
    low, high = BRIGHTNESS_RANGE
    for name in dataset.data_vars:
        if name.upper().startswith(("IR_", "WV_")):
            dataset[name] = dataset[name].where((dataset[name] > low) & (dataset[name] < high))
    return dataset


def open_seviri(path: Path, channels=SEVIRI_CHANNELS, resolution=None, area_extent=None):
    """MSG SEVIRI native (.nat or its Data Store zip): IR 10.8 and WV 6.2 by default.

    With ``resolution`` (degrees) the result is resampled to latitude/longitude with nearest
    neighbour over ``area_extent`` = (west, south, east, north); otherwise it stays in the
    geostationary projection (coordinates x, y in metres, ``crs_wkt`` in the attributes).
    """
    if isinstance(channels, str):
        channels = tuple(channels.split(","))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        nat = extract_native(Path(path), Path(tmp))
        dataset = load_scene([nat], "seviri_l1b_native", channels, resolution, area_extent)
    return mask_brightness(dataset)


FCI_CHANNELS = ("ir_105", "wv_63")


def open_fci(path: Path, channels=FCI_CHANNELS, resolution=None, area_extent=None):
    """MTG FCI level-1c radiances (a Data Store zip of NetCDF chunks, or one chunk).

    Infrared 10.5 um (ir_105) and water vapour 6.3 um (wv_63) by default, as brightness
    temperature. Other satpy FCI names: vis_04 ... vis_09, nir_13, nir_16, nir_22, ir_38, wv_73,
    ir_87, ir_97, ir_123, ir_133.
    """
    from eo_fetch.readers import unpack

    path = Path(path)
    if unpack.sniff(path) == "zip":
        files = [f for f in unpack.unpack_zip(path) if f.suffix.lower() == ".nc"]
    else:
        files = [path]
    if not files:
        raise FileNotFoundError(f"No NetCDF files inside {path.name}")
    if isinstance(channels, str):
        channels = tuple(channels.split(","))
    dataset = load_scene(files, "fci_l1c_nc", channels, resolution, area_extent)
    return mask_brightness(dataset)


SEVIRI_L2_VARIABLES = {
    "clmk": "cloud_mask",
    "clth": "cloud_top_height",
    "aese": "aerosol_optical_thickness_vis06",
    "crmn": "vis_refl_06",
    "firg": "active_fires",
    "mpeg": "instantaneous_rain_rate",
    "ocae": "pixel_scene_type",
}


def open_seviri_l2(path: Path, channels=None, resolution=None, area_extent=None):
    """MSG SEVIRI level-2 GRIB products (cloud mask, cloud top height, MPE rain rate, ...).

    Loads the product's main variable unless ``channels`` names others. Needs eccodes.
    """
    path = Path(path)
    if channels is None:
        match = re.search(r"-SEVI-MSG([A-Z]{4})-", path.name)
        key = match.group(1).lower() if match else ""
        if key not in SEVIRI_L2_VARIABLES:
            raise ValueError(f"Unknown SEVIRI L2 product in {path.name}; give channels=...")
        channels = (SEVIRI_L2_VARIABLES[key],)
    if isinstance(channels, str):
        channels = tuple(channels.split(","))
    return load_scene([path], "seviri_l2_grib", channels, resolution, area_extent)


def open_goes(path: Path, channels=None, resolution=None, area_extent=None):
    """GOES ABI L1b radiances or L2 products.

    Single-channel files (L1b, CMIP) load their own channel; multi-channel MCMIP files load C13
    (10.3 um) unless ``channels`` says otherwise.
    """
    path = Path(path)
    reader = goes_reader(path.name)
    if channels is None:
        own = goes_channel(path.name)
        if own or "cmip" in path.name.lower():
            channels = (own or "C13",)
        else:
            raise ValueError("Give the variables to load with channels=... for this GOES product")
    if isinstance(channels, str):
        channels = tuple(channels.split(","))
    return load_scene([path], reader, channels, resolution, area_extent)
