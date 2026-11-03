"""Spike 8: show the raw HTML of a few DWD directory listings (format of dates and sizes)."""

from __future__ import annotations

import requests
import truststore

BASE = "https://opendata.dwd.de"
PATHS = [
    "/weather/radar/radolan/yw/",
    "/climate_environment/CDC/grids_germany/5_minutes/",
    "/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/recent/",
    "/weather/nwp/icon-d2/grib/",
]
SHOW = 14


def main() -> None:
    truststore.inject_into_ssl()
    for path in PATHS:
        print("=" * 100)
        print(path)
        try:
            response = requests.get(BASE + path, timeout=60)
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"  {type(error).__name__}: {error}")
            continue
        print(f"  content-type: {response.headers.get('content-type')}, {len(response.text)} chars")
        lines = response.text.splitlines()
        print(f"  {len(lines)} lines; first {SHOW}:")
        for line in lines[:SHOW]:
            print("   |", line[:160])
        print("  last 3:")
        for line in lines[-3:]:
            print("   |", line[:160])


if __name__ == "__main__":
    main()
