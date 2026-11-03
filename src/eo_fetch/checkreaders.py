"""Download the smallest recent file of each provider product and try to open it."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eo_fetch.download import download_items
from eo_fetch.models import Query
from eo_fetch.providers import ProviderInfo, all_providers
from eo_fetch.readers import NoReaderError, detect_format, open_data, resolve, summarize

# Files that are documentation or indexes, never the data of a product.
NOT_DATA = (".html", ".htm", ".txt", ".pdf", ".md", ".idx", ".log", ".bz2.log", ".sha256", ".md5")


def is_data(name: str) -> bool:
    lowered = name.lower()
    return not lowered.endswith(NOT_DATA) and not lowered.startswith(("readme", "content.log"))


@dataclass(frozen=True)
class Row:
    provider: str
    product: str
    status: str  # ok, no reader, fail, skip
    format: str = ""
    detail: str = ""


def short(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}"[:120]


def check_product(
    info: ProviderInfo,
    alias: str,
    backend,
    dest: Path,
    days: int,
    max_mb: float,
    candidates: int = 20,
    now: datetime | None = None,
) -> Row:
    """Find files, download the smallest readable-looking one under ``max_mb`` and open it."""
    end = now or datetime.now(UTC)
    try:
        items, where = find_candidates(
            backend, info.name, info.products[alias], end, days, candidates
        )
    except Exception as error:
        return Row(info.name, alias, "skip", detail=f"search failed: {short(error)}")
    sized = [item for item in items if (item.expected_size or 0) > 0]
    small = [item for item in sized if item.expected_size <= max_mb * 1e6]
    if not items:
        return Row(info.name, alias, "skip", detail="no files found (also not in subfolders)")
    if not small:
        return Row(info.name, alias, "skip", detail=f"all candidates larger than {max_mb:g} MB")
    pool = [item for item in small if detect_format(item.filename)] or small
    item = min(pool, key=lambda candidate: candidate.expected_size)
    folder = dest / info.name / alias
    result = download_items(backend, [item], folder, retries=2)[0]
    if result.status == "failed":
        return Row(info.name, alias, "fail", detail=f"download: {result.error}"[:120])
    try:
        format_name = "+".join(sorted({name for name, _ in resolve(result.path)}))
    except Exception:
        format_name = ""
    try:
        dataset = open_data(result.path)
    except NoReaderError as error:
        return Row(info.name, alias, "no reader", format_name, short(error))
    except Exception as error:
        return Row(info.name, alias, "fail", format_name, f"open: {short(error)}")
    if not dataset.data_vars:
        return Row(info.name, alias, "fail", format_name, "opened, but holds no variables")
    first = summarize(dataset).splitlines()[0]
    note = "" if where == info.products[alias] else f"  (in {where})"
    return Row(info.name, alias, "ok", format_name, f"{result.path.name}  {first}{note}")


MAX_DESCENT = 4


def find_candidates(backend, provider: str, product: str, end: datetime, days: int, limit: int):
    """Recent files first; if there are none, files of the newest-named subfolder (up to 4 deep).

    Returns the items and the folder they were found in.
    """
    window = Query(
        provider=provider,
        product=product,
        start=end - timedelta(days=days),
        end=end + timedelta(days=1),
        limit=limit,
    )
    items = [item for item in backend.search(window) if is_data(item.filename)]
    if items:
        return items, product
    current = product
    for _ in range(MAX_DESCENT):
        try:
            found = backend.search(Query(provider=provider, product=current, limit=limit))
        except ValueError:  # e.g. the GOES layout cannot list without a time range
            return [], current
        items = [item for item in found if is_data(item.filename)]
        if items:
            return items, current
        folders = getattr(backend, "folders_seen", [])
        if not folders:
            return [], current
        current = sorted(folders)[-1].rstrip("/")
    return [], current


def run(
    build_backend: Callable[[ProviderInfo], object],
    dest: Path,
    only: Sequence[str] = (),
    days: int = 3,
    max_mb: float = 300.0,
    on_row: Callable[[Row], None] | None = None,
) -> list[Row]:
    """Check every product alias, or those in ``only`` (``provider`` or ``provider/alias``)."""
    rows = []
    for info in all_providers():
        if info.name == "local" or not info.products:
            continue
        for alias in info.products:
            if only and info.name not in only and f"{info.name}/{alias}" not in only:
                continue
            try:
                backend = build_backend(info)
                row = check_product(info, alias, backend, dest, days, max_mb)
            except Exception as error:
                row = Row(info.name, alias, "skip", detail=short(error))
            rows.append(row)
            if on_row:
                on_row(row)
    return rows
