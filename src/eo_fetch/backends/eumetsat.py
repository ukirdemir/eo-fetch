"""EUMETSAT Data Store backend (any of its collections) built on the eumdac library."""

from __future__ import annotations

import os
import shutil
from datetime import UTC
from itertools import islice
from pathlib import Path

from eo_fetch.models import BBox, Item, Query

PROBE_BYTES = "bytes=0-1023"


def bbox_to_wkt(bbox: BBox) -> str:
    """Return a closed WKT polygon for a (west, south, east, north) box."""
    west, south, east, north = bbox
    ring = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


def load_credentials() -> tuple[str, str]:
    """Read the consumer key and secret from the environment or the eumdac credentials file."""
    key, secret = os.environ.get("EUMETSAT_KEY"), os.environ.get("EUMETSAT_SECRET")
    if key and secret:
        return key, secret
    path = Path.home() / ".eumdac" / "credentials"
    if not path.is_file():
        raise RuntimeError(
            "No EUMETSAT credentials: set EUMETSAT_KEY and EUMETSAT_SECRET, or run "
            "`eumdac set-credentials KEY SECRET`."
        )
    key, secret = path.read_text().strip().split(",")[:2]
    return key.strip(), secret.strip()


class EumetsatBackend:
    """Search and download from any collection of the EUMETSAT Data Store.

    ``query.product`` is the collection id, for example ``EO:EUM:DAT:MSG:HRSEVIRI``. Use
    ``collections()`` to list what exists. Access to the files of a collection depends on the
    licence of your account; ``doctor()`` shows which collections answer.
    """

    name = "eumetsat"
    max_connections = 2  # the Data Store throttled us at 4 parallel connections

    def __init__(self) -> None:
        self._store = None
        self._token = None

    def datastore(self):
        """Return a Data Store client (created on first use)."""
        if self._store is None:
            import eumdac

            self._token = eumdac.AccessToken(load_credentials())
            self._store = eumdac.DataStore(self._token)
        return self._store

    def collections(self, text: str = "") -> list[tuple[str, str]]:
        """Return (id, title) of every collection whose id or title contains ``text``."""
        wanted = text.lower()
        found = []
        for collection in self.datastore().collections:
            ident, title = str(collection), str(collection.title)
            if wanted in ident.lower() or wanted in title.lower():
                found.append((ident, title))
        return sorted(found)

    def search(self, query: Query) -> list[Item]:
        if not query.product:
            raise ValueError(
                "EUMETSAT search needs --product with a collection id "
                "(list them with `eo-fetch collections --provider eumetsat`)."
            )
        arguments = {}
        if query.start:
            arguments["dtstart"] = query.start
        if query.end:
            arguments["dtend"] = query.end
        if query.bbox:
            arguments["geo"] = bbox_to_wkt(query.bbox)
        collection = self.datastore().get_collection(query.product)
        products = collection.search(**arguments)
        items = [
            Item(
                provider=query.provider,
                product=query.product,
                key=str(product),
                time=product.sensing_start.replace(tzinfo=UTC),
                meta={"size_kb": str(getattr(product, "size", ""))},
            )
            for product in islice(products, query.limit)
        ]
        return sorted(items, key=lambda item: (item.time, item.key))

    def fetch(self, item: Item, target: Path) -> None:
        product = self.datastore().get_product(product_id=item.key, collection_id=item.product)
        with product.open() as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)

    def doctor(self, collection_ids: tuple[str, ...] = ("EO:EUM:DAT:MSG:HRSEVIRI",)) -> bool:
        """Check credentials and, per collection, whether the newest product can be read."""
        import requests

        try:
            store = self.datastore()
            print(f"  credentials: ok (token valid until {self._token.expiration})")
            print(f"  collections visible: {len(list(store.collections))}")
        except Exception as error:
            print(f"  credentials: FAILED ({type(error).__name__}: {error})")
            return False
        ok = True
        for ident in collection_ids:
            try:
                product = next(iter(store.get_collection(ident).search()))
                response = requests.get(
                    product.url,
                    headers={"Authorization": f"Bearer {self._token}", "Range": PROBE_BYTES},
                    timeout=60,
                )
            except Exception as error:
                print(f"  {ident}: FAILED ({type(error).__name__}: {error})")
                ok = False
                continue
            if response.status_code in (200, 206):
                print(f"  {ident}: download allowed (HTTP {response.status_code})")
            else:
                ok = False
                print(f"  {ident}: HTTP {response.status_code}: {response.text[:300]}")
        return ok
