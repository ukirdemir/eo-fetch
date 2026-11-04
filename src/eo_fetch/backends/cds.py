"""Copernicus Climate Data Store backend (ERA5 and other hourly datasets), via cdsapi.

``search`` plans one request per month of the time range; ``fetch`` submits it to the CDS queue
and downloads the result. Requests can wait in the queue for minutes or hours.
"""

from __future__ import annotations

import json
import os
import re
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eo_fetch.models import Item, Query

DEFAULT_HOURS = ("00:00", "06:00", "12:00", "18:00")
CDS_URL = "https://cds.climate.copernicus.eu/api"


def split_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def month_requests(start: datetime, end: datetime) -> list[tuple[int, int, list[int]]]:
    """(year, month, days) for every month touched by [start, end); only the days inside."""
    result = []
    day = datetime(start.year, start.month, start.day, tzinfo=UTC)
    while day < end:
        last = monthrange(day.year, day.month)[1]
        days = []
        cursor = day
        while cursor < end and cursor.month == day.month:
            days.append(cursor.day)
            cursor += timedelta(days=1)
        result.append((day.year, day.month, days))
        day = datetime(day.year, day.month, last, tzinfo=UTC) + timedelta(days=1)
    return result


def build_request(
    year: int,
    month: int,
    days: list[int],
    variables: list[str],
    hours: list[str],
    bbox,
    data_format: str,
    product_type: str,
    levels: list[str],
    extra: dict,
) -> dict:
    """The CDS request for one month (ERA5 style; ``extra`` can add or replace keys)."""
    request: dict = {
        "variable": variables,
        "year": f"{year:04d}",
        "month": f"{month:02d}",
        "day": [f"{d:02d}" for d in days],
        "time": hours,
        "data_format": data_format,
        "download_format": "unarchived",
    }
    if product_type:
        request["product_type"] = [product_type]
    if levels:
        request["pressure_level"] = levels
    if bbox:
        west, south, east, north = bbox
        request["area"] = [north, west, south, east]  # the CDS wants N, W, S, E
    request.update(extra)
    return request


class CdsBackend:
    """Plan and fetch hourly datasets of the Copernicus Climate Data Store (ERA5 and others).

    ``query.product`` is the dataset name (``reanalysis-era5-single-levels``). Search needs
    ``--start`` and ``--end`` (end exclusive). Parameters: ``variable`` (required, CDS names
    such as ``2m_temperature,total_precipitation``), ``hours`` (default 00:00,06:00,12:00,18:00),
    ``format`` (``grib`` or ``netcdf``; default grib), ``product_type`` (default reanalysis),
    ``level`` (pressure levels in hPa), and ``extra`` (a JSON object merged into the request).
    ``--bbox`` becomes the request's area. Credentials are read by cdsapi from ``~/.cdsapirc``
    (or CDSAPI_URL and CDSAPI_KEY) and never stored by eo-fetch. Accept each dataset's licence
    once on the dataset's page of cds.climate.copernicus.eu.
    """

    name = "cds"
    max_connections = 2
    query_params = frozenset({"variable", "hours", "format", "product_type", "level", "extra"})

    def __init__(self) -> None:
        self._client = None

    def login(self) -> None:
        """Ask for the CDS personal access token (hidden) and save it to ~/.cdsapirc."""
        from eo_fetch.backends.credentials import ask_secret, confirm_overwrite, write_private

        path = Path.home() / ".cdsapirc"
        if not confirm_overwrite(path):
            print("Left unchanged.")
            return
        print("Find your token on your profile page at https://cds.climate.copernicus.eu")
        key = ask_secret("CDS personal access token (input hidden): ")
        write_private(path, f"url: {CDS_URL}\nkey: {key}\n")
        print(f"Saved to {path} (plain text, in your user folder). Delete the file to log out.")
        print("Remember to accept each dataset's licence on its page before downloading.")

    def client(self):
        if self._client is None:
            import cdsapi

            self._client = cdsapi.Client()
        return self._client

    def search(self, query: Query) -> list[Item]:
        if not query.product:
            raise ValueError("CDS search needs --product with a dataset name")
        if not (query.start and query.end):
            raise ValueError("CDS search needs both --start and --end (end is exclusive)")
        variables = split_list(query.params.get("variable") or "")
        if not variables:
            raise ValueError("Give the variables with --param variable=2m_temperature,...")
        hours = split_list(query.params.get("hours") or "") or list(DEFAULT_HOURS)
        data_format = query.params.get("format") or "grib"
        if data_format not in {"grib", "netcdf"}:
            raise ValueError("--param format must be grib or netcdf")
        extra = json.loads(query.params.get("extra") or "{}")
        product_type = query.params.get("product_type", "reanalysis")
        levels = split_list(query.params.get("level") or "")
        suffix = "grib" if data_format == "grib" else "nc"
        label = re.sub(r"[^A-Za-z0-9]+", "-", "-".join(variables))[:60].strip("-")
        items = []
        for year, month, days in month_requests(query.start, query.end):
            request = build_request(
                year=year,
                month=month,
                days=days,
                variables=variables,
                hours=hours,
                bbox=query.bbox,
                data_format=data_format,
                product_type=product_type,
                levels=levels,
                extra=extra,
            )
            items.append(
                Item(
                    provider=query.provider,
                    product=query.product,
                    key=f"{query.product}_{year:04d}{month:02d}_{label}.{suffix}",
                    time=datetime(year, month, days[0], tzinfo=UTC),
                    meta={"request": json.dumps(request)},
                )
            )
        return items[: query.limit] if query.limit else items

    def fetch(self, item: Item, target: Path) -> None:
        request = json.loads(item.meta["request"])
        self.client().retrieve(item.product, request, str(target))

    def doctor(self, collection_ids: tuple[str, ...] = ()) -> bool:
        rc = Path.home() / ".cdsapirc"
        if os.environ.get("CDSAPI_KEY") or rc.is_file():
            print("  credentials: found (CDSAPI_KEY or ~/.cdsapirc), tested when a request runs")
        else:
            print(
                "  credentials: NOT FOUND. Create a free account at "
                "https://cds.climate.copernicus.eu, then run `eo-fetch login --provider cds` "
                "(or write ~/.cdsapirc yourself, or set CDSAPI_URL and CDSAPI_KEY)."
            )
            return False
        print("  licences: accept each dataset's licence on its page, or requests will be refused")
        return True
