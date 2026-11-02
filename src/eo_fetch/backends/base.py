"""The interface every backend implements."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from eo_fetch.models import Item, Query


class Backend(Protocol):
    """A wrapper around one access method (a library or a protocol).

    ``max_connections`` is the number of parallel downloads the service tolerates. ``fetch``
    must write the complete object to ``target``; the downloader passes a temporary name and
    renames it after verification.
    """

    name: str
    max_connections: int

    def search(self, query: Query) -> list[Item]:
        """Return the items matching the query, sorted by time then key."""
        ...

    def fetch(self, item: Item, target: Path) -> None:
        """Write the item to ``target``."""
        ...
