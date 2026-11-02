"""Spike 1: which of the planned backends import in this Python environment?"""

from __future__ import annotations

import importlib
import platform
from importlib import metadata

# (import name, PyPI distribution name)
PACKAGES = [
    ("earthkit.data", "earthkit-data"),
    ("earthkit.plots", "earthkit-plots"),
    ("earthkit.regrid", "earthkit-regrid"),
    ("earthkit.transforms", "earthkit-transforms"),
    ("eccodes", "eccodes"),
    ("cfgrib", "cfgrib"),
    ("earthaccess", "earthaccess"),
    ("eumdac", "eumdac"),
    ("pystac_client", "pystac-client"),
    ("herbie", "herbie-data"),
    ("wetterdienst", "wetterdienst"),
    ("copernicusmarine", "copernicusmarine"),
    ("esgpull", "esgpull"),
    ("cdsapi", "cdsapi"),
    ("satpy", "satpy"),
    ("xarray", "xarray"),
]


def main() -> None:
    print(f"Python {platform.python_version()} on {platform.platform()}")
    for module, dist in PACKAGES:
        try:
            importlib.import_module(module)
            version = metadata.version(dist)
            print(f"  ok       {module:22s} {version}")
        except ModuleNotFoundError:
            print(f"  missing  {module:22s} (pip install {dist})")
        except Exception as error:  # broken binary dependency, for example eccodes
            print(f"  BROKEN   {module:22s} {type(error).__name__}: {str(error)[:120]}")


if __name__ == "__main__":
    main()
