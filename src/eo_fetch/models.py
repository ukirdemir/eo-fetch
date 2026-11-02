"""Provider-neutral types: what to look for (Query) and what was found (Item)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

BBox = tuple[float, float, float, float]  # west, south, east, north in degrees


@dataclass(frozen=True)
class Query:
    """A provider-neutral search. Unused fields are ignored by backends that lack them."""

    provider: str
    product: str = ""
    start: datetime | None = None
    end: datetime | None = None
    bbox: BBox | None = None
    text: str = ""
    limit: int | None = None
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Item:
    """One downloadable object (a file, a granule, a product).

    ``size`` is the exact size in bytes when the provider publishes it; downloads are checked
    against it. ``size_hint`` is an approximate size (for example rounded to kibibytes), used
    only to show totals. ``checksum`` is ``"sha256:<hex>"`` or ``"md5:<hex>"`` when published.
    ``meta`` holds provider-specific details that a backend needs again at fetch time.
    """

    provider: str
    product: str
    key: str
    time: datetime | None = None
    size: int | None = None
    url: str | None = None
    checksum: str | None = None
    meta: Mapping[str, str] = field(default_factory=dict)
    size_hint: int | None = None

    @property
    def expected_size(self) -> int | None:
        """The exact size if known, else the approximate one (for display only)."""
        return self.size if self.size is not None else self.size_hint

    @property
    def filename(self) -> str:
        """A safe local file name derived from the key."""
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", self.key.rsplit("/", 1)[-1])
        return name.strip("._") or "item"
