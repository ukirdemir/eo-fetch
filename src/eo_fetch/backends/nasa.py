"""NASA Earthdata backend: any collection of the Common Metadata Repository, via earthaccess."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from eo_fetch.models import Item, Query

CONCEPT_ID = re.compile(r"C\d+-[A-Z0-9_]+")
SKIP_SUFFIXES = (".xml", ".json", ".html", ".txt", ".pdf", ".png", ".jpg", ".met", ".dmrpp")
CHECKSUMS = {"md5": "md5", "sha1": "sha1", "sha256": "sha256", "sha512": "sha512"}


def value(obj, name: str):
    """An attribute or the result of a method, whichever this earthaccess version offers."""
    attribute = getattr(obj, name)
    return attribute() if callable(attribute) else attribute


def parse_time(text: str | None) -> datetime | None:
    """Parse a CMR timestamp such as ``2026-09-01T00:00:00.000Z``."""
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def version_key(version: str) -> tuple:
    """Sort key for versions like ``7``, ``07B``, ``2.1``: numbers first, then letters."""
    return tuple(int(n) for n in re.findall(r"\d+", version)), version


def split_product(product: str) -> tuple[str, str]:
    """Split ``SHORT_NAME@VERSION`` into its parts (the version may be empty)."""
    short, _, version = product.partition("@")
    return short, version


def pick_link(links: list[str]) -> str | None:
    """The first link that points at data (not metadata or a browse image)."""
    for link in links:
        if link.lower().startswith("http") and not link.lower().endswith(SKIP_SUFFIXES):
            return link
    return None


def file_details(umm: dict, filename: str) -> tuple[int | None, str | None]:
    """Exact size and checksum of ``filename`` when the granule metadata lists them."""
    entries = (umm.get("DataGranule") or {}).get("ArchiveAndDistributionInformation") or []
    for entry in entries:
        if entry.get("Name") != filename:
            continue
        size = entry.get("SizeInBytes")
        checksum = None
        info = entry.get("Checksum") or {}
        algorithm = str(info.get("Algorithm", "")).lower().replace("-", "")
        if info.get("Value") and algorithm in CHECKSUMS:
            checksum = f"{CHECKSUMS[algorithm]}:{info['Value']}"
        return (int(size) if size is not None else None), checksum
    return None, None


def granule_time(umm: dict) -> datetime | None:
    extent = umm.get("TemporalExtent") or {}
    range_time = extent.get("RangeDateTime") or {}
    single = extent.get("SingleDateTime")
    return parse_time(range_time.get("BeginningDateTime") or single)


class NasaBackend:
    """Search and download from any NASA Earthdata collection (the whole CMR catalogue).

    ``query.product`` is a collection short name (``GPM_3IMERGDL``), optionally with a version
    (``GPM_3IMERGDL@07``; the newest version is used otherwise), or a concept id (``C...``).
    ``query.text`` filters granule ids (wildcards ``*`` allowed). Search needs a time range or
    a limit.
    Login uses EARTHDATA_USERNAME/EARTHDATA_PASSWORD, ``~/.netrc`` or asks in the terminal;
    nothing is stored by eo-fetch.
    """

    name = "nasa"
    max_connections = 4

    def __init__(self) -> None:
        self._ea = None
        self._session = None

    def ea(self):
        """The earthaccess module, logged in (on first use)."""
        if self._ea is None:
            import earthaccess

            auth = earthaccess.login()  # environment, ~/.netrc, or a prompt in the terminal
            if not getattr(auth, "authenticated", True):
                raise RuntimeError(
                    "NASA Earthdata login failed. Create a free account at "
                    "https://urs.earthdata.nasa.gov and set EARTHDATA_USERNAME and "
                    "EARTHDATA_PASSWORD, or put them in ~/.netrc."
                )
            self._ea = earthaccess
        return self._ea

    def login(self) -> None:
        """Ask for the Earthdata login once and save it to ~/.netrc (plain text) for later runs."""
        import earthaccess

        auth = earthaccess.login(strategy="interactive", persist=True)
        if not getattr(auth, "authenticated", True):
            raise RuntimeError("NASA Earthdata login failed")
        print("Saved to ~/.netrc (a plain-text file in your user folder). Delete it to log out.")

    def latest_version(self, short_name: str) -> str:
        found = self.ea().search_datasets(short_name=short_name)
        versions = [value(c, "summary").get("version", "") for c in found]
        versions = [v for v in versions if v]
        if not versions:
            raise ValueError(f"No NASA collection with short name {short_name!r}")
        return max(versions, key=version_key)

    def collections(self, text: str = "") -> list[tuple[str, str]]:
        """Collections matching a keyword, as (short_name@version, title)."""
        if not text:
            raise ValueError("Give a keyword with --text; NASA has thousands of collections")
        found = []
        for collection in self.ea().search_datasets(keyword=text, count=100):
            summary = value(collection, "summary")
            title = (collection.get("umm") or {}).get("EntryTitle", "")
            found.append((f"{summary.get('short-name')}@{summary.get('version')}", title))
        return sorted(found)

    def search(self, query: Query) -> list[Item]:
        if not query.product:
            raise ValueError(
                "NASA search needs --product (a short name such as GPM_3IMERGDL, "
                "or find one with `eo-fetch collections --provider nasa --text keyword`)."
            )
        if not (query.start or query.end or query.limit):
            raise ValueError("NASA search needs --start/--end or --limit (collections are huge)")
        arguments: dict = {"count": query.limit if query.limit else -1}
        if CONCEPT_ID.fullmatch(query.product):
            arguments["concept_id"] = query.product
        else:
            short, version = split_product(query.product)
            arguments["short_name"] = short
            arguments["version"] = version or self.latest_version(short)
        if query.start or query.end:
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            arguments["temporal"] = (
                query.start.strftime(fmt) if query.start else None,
                query.end.strftime(fmt) if query.end else None,
            )
        if query.bbox:
            arguments["bounding_box"] = tuple(query.bbox)
        if query.text:
            arguments["granule_ur"] = query.text
        items = []
        for granule in self.ea().search_data(**arguments):
            link = pick_link(value(granule, "data_links"))
            if link is None:
                continue
            filename = link.rsplit("/", 1)[-1]
            umm = granule.get("umm") or {}
            size, checksum = file_details(umm, filename)
            hint = None
            if size is None:
                try:
                    hint = int(float(value(granule, "size")) * 1e6)
                except (TypeError, ValueError):
                    hint = None
            items.append(
                Item(
                    provider=query.provider,
                    product=query.product,
                    key=filename,
                    time=granule_time(umm),
                    size=size,
                    url=link,
                    checksum=checksum,
                    size_hint=hint,
                    meta={"granule": str(umm.get("GranuleUR", ""))},
                )
            )
        if query.end:  # CMR treats the end time as inclusive; eo-fetch queries exclude it
            items = [i for i in items if i.time is None or i.time < query.end]
        items.sort(key=lambda i: (i.time or datetime.min.replace(tzinfo=UTC), i.key))
        return items[: query.limit] if query.limit else items

    def session(self):
        if self._session is None:
            self._session = self.ea().get_requests_https_session()
        return self._session

    def fetch(self, item: Item, target: Path) -> None:
        with self.session().get(item.url, stream=True, timeout=120) as response:
            if response.status_code in (401, 403):
                raise RuntimeError(
                    f"HTTP {response.status_code} from {item.url}: your Earthdata account may "
                    "need to approve the data provider's application (run "
                    "`eo-fetch doctor --provider nasa`)."
                )
            response.raise_for_status()
            with target.open("wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)

    def doctor(self, collection_ids: tuple[str, ...] = ("GPM_3IMERGDL",)) -> bool:
        """Check login and, per collection, whether the newest granule can be read."""
        try:
            self.ea()
            print("  Earthdata login: ok")
        except Exception as error:
            print(f"  Earthdata login: FAILED ({type(error).__name__}: {error})")
            return False
        ok = True
        for ident in collection_ids:
            try:
                items = self.search(Query(provider="nasa", product=ident, limit=1))
                if not items:
                    print(f"  {ident}: no granules found")
                    continue
                response = self.session().get(
                    items[0].url, headers={"Range": "bytes=0-1023"}, timeout=60
                )
            except Exception as error:
                print(f"  {ident}: FAILED ({type(error).__name__}: {error})")
                ok = False
                continue
            if response.status_code in (200, 206):
                print(f"  {ident}: download allowed (HTTP {response.status_code})")
            else:
                ok = False
                print(
                    f"  {ident}: HTTP {response.status_code}. Sign in at "
                    "https://urs.earthdata.nasa.gov, open Applications > Authorized Apps "
                    "and approve the data provider's application (for GES DISC data: "
                    "'NASA GESDISC DATA ARCHIVE'), then try again."
                )
        return ok
