"""Resumable, verified, parallel downloads on top of any backend."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from eo_fetch.backends.base import Backend
from eo_fetch.models import Item

CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Result:
    """The outcome for one item: ``status`` is downloaded, skipped or failed."""

    item: Item
    path: Path | None
    status: str
    size: int = 0
    sha256: str = ""
    seconds: float = 0.0
    error: str = ""


def file_digest(path: Path, algorithm: str = "sha256") -> str:
    """Return the hex digest of a file, read in chunks."""
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def matches(path: Path, item: Item) -> bool:
    """True if the file has the size and checksum the provider announced (when announced)."""
    if not path.is_file():
        return False
    if item.size is not None and path.stat().st_size != item.size:
        return False
    if item.checksum:
        algorithm, _, expected = item.checksum.partition(":")
        return file_digest(path, algorithm) == expected.lower()
    return True


def download_one(
    backend: Backend,
    item: Item,
    dest: Path,
    retries: int,
    backoff: float,
    sleep: Callable[[float], None],
) -> Result:
    """Fetch one item to ``dest``; skip it if a matching file exists; retry on errors."""
    target = dest / item.filename
    started = time.perf_counter()
    if matches(target, item):
        return Result(item, target, "skipped", target.stat().st_size, file_digest(target))
    partial = target.with_name(target.name + ".part")
    error = ""
    for attempt in range(1, retries + 1):
        try:
            partial.unlink(missing_ok=True)
            backend.fetch(item, partial)
            if not matches(partial, item):
                raise OSError("size or checksum does not match what the provider announced")
            partial.replace(target)
            seconds = time.perf_counter() - started
            return Result(
                item, target, "downloaded", target.stat().st_size, file_digest(target), seconds
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            partial.unlink(missing_ok=True)
            if attempt < retries:
                sleep(backoff * attempt)
    return Result(item, None, "failed", error=error, seconds=time.perf_counter() - started)


def download_items(
    backend: Backend,
    items: Sequence[Item],
    dest: Path,
    *,
    workers: int | None = None,
    retries: int = 3,
    backoff: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    on_result: Callable[[Result], None] | None = None,
) -> list[Result]:
    """Download items in parallel, never using more connections than the backend allows.

    Results come back in the order of ``items``. Failures do not stop the others.
    """
    dest.mkdir(parents=True, exist_ok=True)
    limit = backend.max_connections
    pool_size = max(1, min(workers or limit, limit))

    def work(item: Item) -> Result:
        result = download_one(backend, item, dest, retries, backoff, sleep)
        if on_result:
            on_result(result)
        return result

    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        return list(pool.map(work, items))
