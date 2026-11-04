"""EUMETSAT Data Store backend (any of its collections) built on the eumdac library."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path

from eo_fetch.models import BBox, Item, Query

PROBE_BYTES = "bytes=0-1023"


def bbox_to_wkt(bbox: BBox) -> str:
    """Return a closed WKT polygon for a (west, south, east, north) box."""
    west, south, east, north = bbox
    ring = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


def kib_to_bytes(size_kib) -> int | None:
    """Convert the Data Store's product size (kibibytes, rounded) to approximate bytes."""
    try:
        return int(size_kib) * 1024
    except (TypeError, ValueError):
        return None


def load_credentials() -> tuple[str, str]:
    """Read the consumer key and secret from the environment or the eumdac credentials file."""
    key, secret = os.environ.get("EUMETSAT_KEY"), os.environ.get("EUMETSAT_SECRET")
    if key and secret:
        return key, secret
    path = Path.home() / ".eumdac" / "credentials"
    if not path.is_file():
        raise RuntimeError(
            "No EUMETSAT credentials: run `eo-fetch login --provider eumetsat`, or set "
            "EUMETSAT_KEY and EUMETSAT_SECRET."
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

    def login(self) -> None:
        """Ask for the consumer key and secret (secret hidden), save them for eumdac."""
        from eo_fetch.backends.credentials import ask_secret, confirm_overwrite, write_private

        path = Path.home() / ".eumdac" / "credentials"
        if not confirm_overwrite(path):
            print("Left unchanged.")
            return
        print("Find them at https://api.eumetsat.int/api-key (EUMETSAT Data Services account)")
        key = input("Consumer key: ").strip()
        secret = ask_secret("Consumer secret (input hidden): ")
        if not key:
            raise ValueError("Nothing entered")
        write_private(path, f"{key},{secret}\n")
        print(f"Saved to {path} (plain text, in your user folder). Delete the file to log out.")

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
        # The service answers newest first. With a time range the whole answer is listed and
        # sorted, so a limit keeps the earliest products. Without a range, a limit keeps the
        # newest ones (listing a whole archive just to cut it would be wasteful).
        bounded = query.start is not None or query.end is not None
        if not bounded:
            products = islice(products, query.limit)
        items = [
            Item(
                provider=query.provider,
                product=query.product,
                key=str(product),
                time=product.sensing_start.replace(tzinfo=UTC),
                size_hint=kib_to_bytes(getattr(product, "size", None)),
            )
            for product in products
        ]
        items.sort(key=lambda item: (item.time, item.key))
        return items[: query.limit] if query.limit else items

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
        older = datetime.now(UTC) - timedelta(days=2)
        probes = (("newest product", {}), ("product older than 2 days", {"dtend": older}))
        for ident in collection_ids:
            collection = store.get_collection(ident)
            for label, arguments in probes:
                try:
                    product = next(iter(collection.search(**arguments)), None)
                    if product is None:
                        print(f"  {ident}, {label}: none found")
                        continue
                    response = requests.get(
                        product.url,
                        headers={"Authorization": f"Bearer {self._token}", "Range": PROBE_BYTES},
                        timeout=60,
                    )
                except Exception as error:
                    print(f"  {ident}, {label}: FAILED ({type(error).__name__}: {error})")
                    ok = False
                    continue
                if response.status_code in (200, 206):
                    print(f"  {ident}, {label}: download allowed (HTTP {response.status_code})")
                else:
                    ok = False
                    text = response.text[:300]
                    print(f"  {ident}, {label}: HTTP {response.status_code}: {text}")
        return ok
