"""Spike 5: can earthkit-plots draw (a) a regular lat/lon field and (b) a regridded SEVIRI scene?

Needs earthkit-plots, and for part (b) satpy and the SEVIRI zip downloaded earlier by
eo-ml-ready (data/seviri_test/*.zip). Pass its path with --zip.
"""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import xarray as xr


def regular_field() -> xr.DataArray:
    """A synthetic temperature-like field on a regular 1 degree grid."""
    lat = np.arange(90, -91, -1.0)
    lon = np.arange(-180, 180, 1.0)
    values = 288 - 40 * np.abs(np.sin(np.radians(lat)))[:, None] + 3 * np.cos(np.radians(lon))
    return xr.DataArray(
        values,
        coords={"latitude": lat, "longitude": lon},
        dims=("latitude", "longitude"),
        name="t2m",
        attrs={"units": "K"},
    )


def seviri_latlon(zip_path: Path) -> xr.DataArray:
    """Read IR 10.8 um and resample it to a regular 0.05 degree grid over Africa."""
    from pyresample import create_area_def
    from satpy import Scene

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(tmp)
        nat = sorted(Path(tmp).rglob("*.nat"))[0]
        scene = Scene(filenames=[str(nat)], reader="seviri_l1b_native")
        scene.load(["IR_108"])
        target = create_area_def(
            "africa", "EPSG:4326", area_extent=(-14, -4, 18, 26), resolution=0.05
        )
        resampled = scene.resample(target, resampler="nearest")
        values = np.asarray(resampled["IR_108"].values, dtype=np.float32)
        x, y = target.get_proj_vectors()
    return xr.DataArray(
        values,
        coords={"latitude": y, "longitude": x},
        dims=("latitude", "longitude"),
        name="bt_ir108",
        attrs={"units": "K", "long_name": "SEVIRI IR 10.8 um brightness temp."},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None, help="SEVIRI product zip for part (b)")
    parser.add_argument("--out", type=Path, default=Path("spike_plots"))
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True)

    import earthkit.plots as ekp

    chart = ekp.quickplot(regular_field())
    chart.save(args.out / "regular.png")
    print(f"Saved {args.out / 'regular.png'}")

    if args.zip:
        field = seviri_latlon(args.zip)
        print(f"SEVIRI regridded: {field.shape}, min {float(field.min()):.1f} K")
        chart = ekp.quickplot(field, domain="Africa")
        chart.save(args.out / "seviri.png")
        print(f"Saved {args.out / 'seviri.png'}")


if __name__ == "__main__":
    main()
