"""A backend for files in a local or network folder (also used to test the downloader)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from eo_fetch.models import Item, Query


class LocalBackend:
    """Lists and copies files below ``root``; the query text is a glob pattern."""

    name = "local"
    max_connections = 4

    def __init__(self, root: str = ".") -> None:
        self.root = Path(root)

    def search(self, query: Query) -> list[Item]:
        pattern = query.text or "*"
        items = []
        for path in self.root.rglob(pattern):
            if not path.is_file():
                continue
            stat = path.stat()
            time = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            if (query.start and time < query.start) or (query.end and time >= query.end):
                continue
            items.append(
                Item(
                    provider=query.provider,
                    product=query.product or "files",
                    key=path.relative_to(self.root).as_posix(),
                    time=time,
                    size=stat.st_size,
                    url=path.resolve().as_uri(),
                )
            )
        items.sort(key=lambda item: (item.time, item.key))
        return items[: query.limit] if query.limit else items

    def fetch(self, item: Item, target: Path) -> None:
        shutil.copyfile(self.root / item.key, target)
