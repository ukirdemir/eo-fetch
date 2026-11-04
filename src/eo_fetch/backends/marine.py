"""Copernicus Marine (CMEMS) backend: ocean datasets subset by area, depth and time.

``search`` plans one request per month; ``fetch`` runs the toolbox's ``subset`` for it. The
toolbox stores your login itself (``copernicusmarine login``).
"""

from __future__ import annotations

import inspect
import re
import shutil
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eo_fetch.models import Item, Query


def split_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def time_chunks(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Month-sized (first, last) instants covering [start, end); the last is inclusive."""
    chunks = []
    cursor = start
    while cursor < end:
        last_day = monthrange(cursor.year, cursor.month)[1]
        month_end = datetime(cursor.year, cursor.month, last_day, 23, 59, 59, tzinfo=UTC)
        chunk_end = min(month_end, end - timedelta(seconds=1))
        chunks.append((cursor, chunk_end))
        cursor = month_end + timedelta(seconds=1)
    return chunks


def subset_arguments(function, request: dict, directory: Path) -> dict:
    """Keyword arguments for ``copernicusmarine.subset``; options only newer or older toolbox
    versions know are added when the installed one accepts them."""
    arguments = dict(request)
    arguments["output_directory"] = str(directory)
    accepted = set(inspect.signature(function).parameters)
    for name, value in (
        ("force_download", True),  # toolbox 1.x: do not ask for confirmation
        ("overwrite", True),  # toolbox 2.x
        ("disable_progress_bar", True),
    ):
        if name in accepted:
            arguments[name] = value
    return arguments


class MarineBackend:
    """Plan and fetch Copernicus Marine subsets.

    ``query.product`` is a dataset id (find them with ``collections --text``). Search needs
    ``--start`` and ``--end`` (end exclusive). Parameters: ``variables`` (comma list; default: all
    variables of the dataset), ``min_depth`` and ``max_depth`` in metres, ``version``. ``--bbox``
    limits the area. Log in once with ``eo-fetch login --provider copernicus-marine``.
    """

    name = "marine"
    max_connections = 2
    query_params = frozenset({"variables", "min_depth", "max_depth", "version"})

    def __init__(self) -> None:
        self._cm = None

    def toolbox(self):
        if self._cm is None:
            import copernicusmarine

            self._cm = copernicusmarine
        return self._cm

    def login(self) -> None:
        """Let the toolbox ask for username and password and save them in its own file."""
        self.toolbox().login()
        print("Saved by the Copernicus Marine toolbox in ~/.copernicusmarine (plain text).")

    def collections(self, text: str = "") -> list[tuple[str, str]]:
        if not text:
            raise ValueError("Give a keyword with --text, for example --text temperature")
        catalogue = self.toolbox().describe(contains=[text])
        found = []
        for product in getattr(catalogue, "products", []):
            title = getattr(product, "title", "") or ""
            for dataset in getattr(product, "datasets", []):
                ident = getattr(dataset, "dataset_id", None)
                if ident:
                    found.append((ident, title))
        return sorted(set(found))

    def search(self, query: Query) -> list[Item]:
        if not query.product:
            raise ValueError("Copernicus Marine search needs --product with a dataset id")
        if not (query.start and query.end):
            raise ValueError("Copernicus Marine search needs both --start and --end")
        variables = split_list(query.params.get("variables") or "")
        label = re.sub(r"[^A-Za-z0-9]+", "-", "-".join(variables))[:40].strip("-") or "all"
        items = []
        for first, last in time_chunks(query.start, query.end):
            request: dict = {
                "dataset_id": query.product,
                "start_datetime": first.strftime("%Y-%m-%dT%H:%M:%S"),
                "end_datetime": last.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            if variables:
                request["variables"] = variables
            if query.params.get("version"):
                request["dataset_version"] = query.params["version"]
            if query.bbox:
                west, south, east, north = query.bbox
                request.update(
                    minimum_longitude=west,
                    maximum_longitude=east,
                    minimum_latitude=south,
                    maximum_latitude=north,
                )
            for key in ("min_depth", "max_depth"):
                if query.params.get(key):
                    request[key.replace("min_", "minimum_").replace("max_", "maximum_")] = float(
                        query.params[key]
                    )
            items.append(
                Item(
                    provider=query.provider,
                    product=query.product,
                    key=f"{query.product}_{first:%Y%m%d}-{last:%Y%m%d}_{label}.nc",
                    time=first,
                    meta={"request": repr(request)},
                )
            )
        return items[: query.limit] if query.limit else items

    def fetch(self, item: Item, target: Path) -> None:
        import ast

        request = ast.literal_eval(item.meta["request"])
        toolbox = self.toolbox()
        workdir = target.parent / (target.name + ".dl")
        workdir.mkdir(parents=True, exist_ok=True)
        try:
            request["output_filename"] = "subset.nc"
            toolbox.subset(**subset_arguments(toolbox.subset, request, workdir))
            (workdir / "subset.nc").replace(target)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def doctor(self, collection_ids: tuple[str, ...] = ()) -> bool:
        try:
            catalogue = self.toolbox().describe(contains=["temperature"])
            count = len(getattr(catalogue, "products", []))
            print(f"  catalogue reachable: {count} products match 'temperature'")
        except Exception as error:
            print(f"  catalogue: FAILED ({type(error).__name__}: {error})")
            return False
        print("  login is checked when a subset runs; use `eo-fetch login --provider ...`")
        return True
