"""Anonymous S3 backend for open-data buckets (NOAA, and any other public bucket)."""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
from itertools import islice
from pathlib import Path

from eo_fetch.models import Item, Query
from eo_fetch.timeguess import guess_time

__all__ = ["S3Backend", "goes_prefixes", "goes_time", "guess_time", "split_product"]

# GOES-R file names carry the scan start as _sYYYYDDDHHMMSSs (day of year, tenths of a second).
GOES_TIME = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})\d")


def split_product(product: str) -> tuple[str, str]:
    """Split ``bucket/prefix`` into the bucket name and the prefix below it."""
    bucket, _, root = product.strip("/").partition("/")
    if not bucket:
        raise ValueError("S3 product must look like 'bucket/prefix', e.g. noaa-goes19/GLM-L2-LCFA")
    return bucket, root


def goes_time(name: str) -> datetime | None:
    """Return the scan start time encoded in a GOES-R file name, if there is one."""
    match = GOES_TIME.search(name)
    if not match:
        return None
    year, day, hour, minute, second = (int(group) for group in match.groups())
    return datetime(year, 1, 1, tzinfo=UTC) + timedelta(
        days=day - 1, hours=hour, minutes=minute, seconds=second
    )


def goes_prefixes(bucket: str, root: str, start: datetime, end: datetime) -> list[str]:
    """One ``root/year/day-of-year/hour/`` prefix for every hour in [start, end)."""
    prefixes = []
    current = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    while current < end:
        day = current.timetuple().tm_yday
        prefixes.append(f"{bucket}/{root}/{current.year}/{day:03d}/{current.hour:02d}/")
        current += timedelta(hours=1)
    return prefixes


class S3Backend:
    """List and download objects from public S3 buckets without credentials.

    ``query.product`` is ``bucket/prefix``. With a time range and ``layout=goes`` (the default
    for buckets whose name starts with ``noaa-goes``) only the hourly folders in the range are
    listed. Otherwise give ``--param prefix=...`` for the folder to list; ``--param depth=N``
    also lists N levels of subfolders. ``query.text`` is a glob applied to the file names. Sizes
    are exact, so downloads are verified against them. ``folders_seen`` holds the subfolders met
    during the last search, so that an empty result can point at where the files are.
    """

    name = "s3"
    max_connections = 8
    query_params = frozenset({"prefix", "layout", "depth"})

    def __init__(self) -> None:
        self._fs = None
        self.folders_seen: list[str] = []

    def filesystem(self):
        """Return an anonymous s3fs filesystem (created on first use)."""
        if self._fs is None:
            import s3fs

            self._fs = s3fs.S3FileSystem(anon=True)
        return self._fs

    def search(self, query: Query) -> list[Item]:
        if not query.product:
            raise ValueError("S3 search needs --product bucket/prefix (or a provider alias)")
        bucket, root = split_product(query.product)
        layout = query.params.get("layout") or ("goes" if bucket.startswith("noaa-goes") else "")
        if layout == "goes":
            if not (query.start and query.end):
                raise ValueError("The goes layout needs both --start and --end")
            prefixes = goes_prefixes(bucket, root, query.start, query.end)
        else:
            extra = query.params.get("prefix", "").strip("/")
            prefixes = [f"{bucket}/{root}/{extra}/".replace("//", "/")]
        fs = self.filesystem()
        depth = int(query.params["depth"]) if query.params.get("depth") else None
        self.folders_seen = []
        items = []
        for prefix in prefixes:
            try:
                if depth:
                    entries = list(fs.find(prefix, maxdepth=depth, detail=True).values())
                else:
                    entries = fs.ls(prefix, detail=True)
            except FileNotFoundError:
                continue
            except PermissionError as error:
                raise RuntimeError(
                    f"Access denied listing s3://{prefix}. The bucket may not allow anonymous "
                    "listing, or its name or layout may have changed."
                ) from error
            self.folders_seen += [e["name"] for e in entries if e["type"] == "directory"]
            for entry in entries:
                if entry["type"] != "file":
                    continue
                name = entry["name"].rsplit("/", 1)[-1]
                if query.text and not fnmatch(name, query.text):
                    continue
                time = goes_time(name) if layout == "goes" else guess_time(entry["name"])
                if (query.start or query.end) and time is None:
                    continue  # with a time range, files whose time is unknown cannot qualify
                if time and query.start and time < query.start:
                    continue
                if time and query.end and time >= query.end:
                    continue
                items.append(
                    Item(
                        provider=query.provider,
                        product=query.product,
                        key=entry["name"],
                        time=time,
                        size=int(entry["size"]),
                        url=f"s3://{entry['name']}",
                    )
                )
        items.sort(key=lambda item: (item.time or datetime.min.replace(tzinfo=UTC), item.key))
        return list(islice(items, query.limit))

    def fetch(self, item: Item, target: Path) -> None:
        with self.filesystem().open(item.key, "rb") as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)
