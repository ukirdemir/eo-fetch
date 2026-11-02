"""Spike 3: list the first levels of the DWD open data tree (https://opendata.dwd.de)."""

from __future__ import annotations

import re

import requests
import truststore

BASE = "https://opendata.dwd.de"
PATHS = [
    "/",
    "/climate_environment/CDC/",
    "/climate_environment/CDC/grids_germany/",
    "/climate_environment/CDC/observations_germany/",
    "/weather/",
    "/weather/radar/",
    "/weather/nwp/",
]
LINK = re.compile(r'<a href="([^"?][^"]*)"')


def list_directory(path: str) -> list[str]:
    response = requests.get(BASE + path, timeout=60)
    response.raise_for_status()
    return [href for href in LINK.findall(response.text) if not href.startswith(("/", ".."))]


def main() -> None:
    truststore.inject_into_ssl()  # the DWD certificate chain needs the Windows store
    for path in PATHS:
        try:
            entries = list_directory(path)
        except requests.RequestException as error:
            print(f"{path}: {type(error).__name__}: {error}")
            continue
        folders = [e for e in entries if e.endswith("/")]
        files = [e for e in entries if not e.endswith("/")]
        print(f"{path}: {len(folders)} folders, {len(files)} files")
        print("   folders:", ", ".join(folders[:25]) + (" ..." if len(folders) > 25 else ""))


if __name__ == "__main__":
    main()
