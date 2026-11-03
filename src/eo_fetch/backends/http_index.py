"""Backend for plain HTTP directory listings (nginx and Apache autoindex), e.g. DWD open data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from itertools import islice
from pathlib import Path
from urllib.parse import unquote

from eo_fetch import __version__
from eo_fetch.models import Item, Query
from eo_fetch.timeguess import guess_time

MAX_FOLDERS = 300
USER_AGENT = f"eo-fetch/{__version__} (+https://github.com/ukirdemir/eo-fetch)"
MONTHS = {
    name: number
    for number, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}
# <a href="NAME">NAME</a>     31-Oct-2026 23:00:26     27631      (size is "-" for folders)
LINE = re.compile(
    r'<a href="(?P<href>[^"]+)">[^<]*</a>\s+'
    r"(?P<day>\d{2})-(?P<month>[A-Za-z]{3})-(?P<year>\d{4}) (?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<size>\d+|-)"
)
_truststore_injected = False


@dataclass(frozen=True)
class IndexEntry:
    """One line of a directory listing."""

    name: str
    is_dir: bool
    modified: datetime | None
    size: int | None


def parse_index(html: str) -> list[IndexEntry]:
    """Parse an autoindex page into entries; the parent link and sort links are skipped."""
    entries = []
    for match in LINE.finditer(html):
        href = unquote(match["href"])
        if href.startswith(("../", "/", "?", "http")):
            continue
        month = MONTHS.get(match["month"].title())
        modified = None
        if month:
            hour, minute, second = (int(part) for part in match["time"].split(":"))
            modified = datetime(
                int(match["year"]), month, int(match["day"]), hour, minute, second, tzinfo=UTC
            )
        size = None if match["size"] == "-" else int(match["size"])
        entries.append(IndexEntry(href, href.endswith("/"), modified, size))
    return entries


class HttpIndexBackend:
    """List and download files from an HTTP server that publishes directory indexes.

    ``base_url`` comes from the provider card. ``query.product`` is the folder below it;
    ``--param prefix=sub/folder`` goes further down and ``--param depth=N`` also lists N levels
    of subfolders (at most 300 folders per search). ``query.text`` is a glob on file names.
    Sizes are exact, so downloads are verified against them. The time of a file is taken from its
    name or folder when it contains a date, otherwise from the server's modification time.
    """

    name = "http-index"
    max_connections = 4
    query_params = frozenset({"prefix", "depth"})

    def __init__(self, base_url: str = "") -> None:
        if not base_url:
            raise ValueError("The http-index backend needs a base_url (set by the provider card)")
        self.base_url = base_url.rstrip("/")
        self._session = None
        self.folders_seen: list[str] = []

    def session(self):
        """Return a requests session (created on first use, using the system certificates)."""
        global _truststore_injected
        if self._session is None:
            import requests

            if not _truststore_injected:
                try:
                    import truststore

                    truststore.inject_into_ssl()
                except ImportError:
                    pass
                _truststore_injected = True
            self._session = requests.Session()
            self._session.headers["User-Agent"] = USER_AGENT
        return self._session

    def list_folder(self, path: str) -> list[IndexEntry]:
        url = f"{self.base_url}/{path.strip('/')}/" if path.strip("/") else f"{self.base_url}/"
        response = self.session().get(url, timeout=60)
        if response.status_code == 404:
            raise FileNotFoundError(f"Not found: {url}")
        response.raise_for_status()
        return parse_index(response.text)

    def search(self, query: Query) -> list[Item]:
        parts = (query.product, query.params.get("prefix", ""))
        root = "/".join(part.strip("/") for part in parts if part.strip("/"))
        depth = int(query.params.get("depth") or 1)
        self.folders_seen = []
        items = []
        queue = [(root, 1)]
        listed = 0
        while queue:
            path, level = queue.pop(0)
            listed += 1
            if listed > MAX_FOLDERS:
                raise RuntimeError(
                    f"More than {MAX_FOLDERS} folders to list: narrow the product or prefix, "
                    "or lower depth."
                )
            for entry in self.list_folder(path):
                full = f"{path}/{entry.name}" if path else entry.name
                if entry.is_dir:
                    folder = full.rstrip("/")
                    self.folders_seen.append(folder)
                    if level < depth:
                        queue.append((folder, level + 1))
                    continue
                if query.text and not fnmatch(entry.name, query.text):
                    continue
                time = guess_time(full) or entry.modified
                if (query.start or query.end) and time is None:
                    continue
                if time and query.start and time < query.start:
                    continue
                if time and query.end and time >= query.end:
                    continue
                items.append(
                    Item(
                        provider=query.provider,
                        product=query.product,
                        key=full,
                        time=time,
                        size=entry.size,
                        url=f"{self.base_url}/{full}",
                    )
                )
        items.sort(key=lambda item: (item.time or datetime.min.replace(tzinfo=UTC), item.key))
        return list(islice(items, query.limit))

    def fetch(self, item: Item, target: Path) -> None:
        with self.session().get(item.url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with target.open("wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)
