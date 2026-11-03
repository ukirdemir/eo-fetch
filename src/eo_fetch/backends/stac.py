"""STAC catalogue backend (Planetary Computer, AWS Earth Search, Copernicus Data Space, ...).

One downloadable object is one asset of one STAC item, so a query for ``B04,B08`` of ten scenes
lists twenty files.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from eo_fetch.models import Item, Query

CDSE_S3_ENDPOINT = "https://eodata.dataspace.copernicus.eu"


def datetime_range(start: datetime | None, end: datetime | None) -> str | None:
    """A STAC datetime interval (open ends as ``..``), or None without bounds."""
    if not (start or end):
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return f"{start.strftime(fmt) if start else '..'}/{end.strftime(fmt) if end else '..'}"


def asset_filename(item_id: str, asset_key: str, href: str) -> str:
    """A file name like ``S2A_..._B04.tif``: item id, asset key and the extension of the link."""
    name = urlparse(href).path.rsplit("/", 1)[-1]
    suffix = "".join(Path(name).suffixes[-2:]) if "." in name else ""
    if not re.fullmatch(r"(\.[A-Za-z0-9]{1,6}){0,2}", suffix):
        suffix = Path(name).suffix
    return f"{item_id}_{asset_key}{suffix}"


def choose_assets(asset_keys: list[str], wanted: list[str], item_id: str) -> list[str]:
    """The asset keys to download: those asked for, else ``data`` or ``visual`` if present."""
    if wanted:
        missing = [key for key in wanted if key not in asset_keys]
        if missing:
            raise ValueError(
                f"Item {item_id} has no asset {', '.join(missing)}. "
                f"Available: {', '.join(sorted(asset_keys))}"
            )
        return wanted
    for default in ("data", "visual"):
        if default in asset_keys:
            return [default]
    raise ValueError(
        f"Choose assets with --param assets=KEY[,KEY]. Available in {item_id}: "
        f"{', '.join(sorted(asset_keys))}"
    )


class StacBackend:
    """Search a STAC API and download item assets over HTTP(S) or S3.

    ``query.product`` is a collection id; ``--param assets=B04,B08`` picks the assets (default:
    ``data`` or ``visual`` when the items have one). ``query.limit`` counts files. ``sign`` is
    ``planetary-computer`` for catalogues whose links need a short-lived signature. Links to S3
    objects use anonymous access, or the Copernicus Data Space keys in CDSE_S3_KEY and
    CDSE_S3_SECRET when ``s3_endpoint`` is set.
    """

    name = "stac"
    max_connections = 4
    query_params = frozenset({"assets"})

    def __init__(self, catalog_url: str = "", sign: str = "", s3_endpoint: str = "") -> None:
        if not catalog_url:
            raise ValueError("The stac backend needs a catalog_url (set by the provider card)")
        self.catalog_url = catalog_url
        self.sign = sign
        self.s3_endpoint = s3_endpoint
        self._client = None
        self._session = None
        self._fs = None

    def client(self):
        if self._client is None:
            from pystac_client import Client

            self._client = Client.open(self.catalog_url)
        return self._client

    def collections(self, text: str = "") -> list[tuple[str, str]]:
        wanted = text.lower()
        found = []
        for collection in self.client().get_collections():
            title = collection.title or ""
            if wanted in collection.id.lower() or wanted in title.lower():
                found.append((collection.id, title))
        return sorted(found)

    def signed(self, href: str) -> str:
        if self.sign == "planetary-computer":
            import planetary_computer

            return planetary_computer.sign(href)
        return href

    def search(self, query: Query) -> list[Item]:
        if not query.product:
            raise ValueError(
                "STAC search needs --product with a collection id "
                "(list them with `eo-fetch collections --provider ...`)."
            )
        arguments: dict = {"collections": [query.product]}
        interval = datetime_range(query.start, query.end)
        if interval:
            arguments["datetime"] = interval
        if query.bbox:
            arguments["bbox"] = list(query.bbox)
        if query.limit:
            arguments["max_items"] = query.limit
        wanted = [a for a in (query.params.get("assets") or "").split(",") if a]
        files: list[Item] = []
        for stac_item in self.client().search(**arguments).items():
            keys = choose_assets(list(stac_item.assets), wanted, stac_item.id)
            for key in keys:
                asset = stac_item.assets[key]
                extra = asset.extra_fields or {}
                size = extra.get("file:size")
                moment = stac_item.datetime
                if moment is not None and moment.tzinfo is None:
                    moment = moment.replace(tzinfo=UTC)
                files.append(
                    Item(
                        provider=query.provider,
                        product=query.product,
                        key=asset_filename(stac_item.id, key, asset.href),
                        time=moment,
                        url=asset.href,
                        size_hint=int(size) if size is not None else None,
                        meta={"item": stac_item.id, "asset": key},
                    )
                )
        files.sort(key=lambda i: (i.time or datetime.min.replace(tzinfo=UTC), i.key))
        return files[: query.limit] if query.limit else files

    def session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def filesystem(self):
        if self._fs is None:
            import s3fs

            if self.s3_endpoint:
                key, secret = os.environ.get("CDSE_S3_KEY"), os.environ.get("CDSE_S3_SECRET")
                if not (key and secret):
                    raise RuntimeError(
                        "Copernicus Data Space downloads need S3 keys: create them at "
                        "https://eodata-s3keysmanager.dataspace.copernicus.eu and set "
                        "CDSE_S3_KEY and CDSE_S3_SECRET."
                    )
                self._fs = s3fs.S3FileSystem(
                    key=key, secret=secret, client_kwargs={"endpoint_url": self.s3_endpoint}
                )
            else:
                self._fs = s3fs.S3FileSystem(anon=True)
        return self._fs

    def fetch(self, item: Item, target: Path) -> None:
        href = item.url or ""
        if href.startswith("s3://"):
            self.filesystem().get_file(href[len("s3://") :], str(target))
            return
        with self.session().get(self.signed(href), stream=True, timeout=120) as response:
            response.raise_for_status()
            with target.open("wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)

    def doctor(self, collection_ids: tuple[str, ...] = ()) -> bool:
        try:
            count = len(list(self.client().get_collections()))
            print(f"  catalogue reachable: {count} collections at {self.catalog_url}")
        except Exception as error:
            print(f"  catalogue: FAILED ({type(error).__name__}: {error})")
            return False
        if self.sign == "planetary-computer":
            try:
                import planetary_computer  # noqa: F401

                print("  signing: planetary-computer package available")
            except ImportError:
                print("  signing: FAILED (pip install planetary-computer)")
                return False
        if self.s3_endpoint:
            have = bool(os.environ.get("CDSE_S3_KEY") and os.environ.get("CDSE_S3_SECRET"))
            print(f"  CDSE S3 keys in environment: {'yes' if have else 'NO (needed to download)'}")
            return have
        return True
