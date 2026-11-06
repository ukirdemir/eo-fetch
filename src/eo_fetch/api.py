"""The Python API: ``import eo_fetch as eof``.

    import eo_fetch as eof

    found = eof.search("dwd", "radolan-yw", limit=2)
    eof.download(found, "data/dwd")
    ds = eof.open("data/dwd/raa01-yw_10000-2611032225-dwd---bin.hdf5")

Everything the command line does is available here, with the same names and rules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

from eo_fetch.backends import backend_factory, get_backend, param_names
from eo_fetch.discovery import ProductMatch, find_products
from eo_fetch.downloader import Result, download_items
from eo_fetch.manifest import build_manifest, verify_manifest, write_manifest
from eo_fetch.models import Item, Query
from eo_fetch.registry import ProviderInfo, all_providers, get_provider


def parse_time(value: str | date | datetime) -> datetime:
    """An ISO string, date or datetime as a timezone-aware datetime (naive values are UTC)."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    else:
        moment = datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def param_text(value: object) -> str:
    """A search parameter as text; lists and tuples become comma-separated values."""
    if isinstance(value, list | tuple | set | frozenset):
        return ",".join(str(part) for part in value)
    return str(value)


def make_backend(info: ProviderInfo, user_params: Mapping[str, str]):
    """Create the provider's backend; unknown parameter names raise ValueError."""
    constructor, search_names = param_names(info.backend)
    unknown = set(user_params) - constructor - search_names
    if getattr(backend_factory(info.backend), "open_params", False):
        unknown = set()  # every other parameter is a search facet
    if unknown:
        accepted = ", ".join(sorted(constructor | search_names)) or "none"
        raise ValueError(
            f"Unknown --param {', '.join(sorted(unknown))} for provider {info.name} "
            f"(accepted: {accepted})"
        )
    return get_backend(info.backend, {**info.backend_params, **user_params})


class Results(list[Item]):
    """The items a search found, plus what is needed to download them.

    It is a normal list of :class:`Item`. Slices and :meth:`where` keep the download context, so
    ``eof.download(found[:3], dest)`` and ``eof.download(found.where(...), dest)`` work.
    """

    def __init__(self, items: Iterable[Item], *, info: ProviderInfo, backend, query: Query):
        super().__init__(items)
        self.info = info
        self.backend = backend
        self.query = query

    def __getitem__(self, index):
        picked = super().__getitem__(index)
        return self.derive(picked) if isinstance(index, slice) else picked

    def derive(self, items: Iterable[Item]) -> Results:
        return Results(items, info=self.info, backend=self.backend, query=self.query)

    def where(self, keep: Callable[[Item], bool]) -> Results:
        """The items for which ``keep(item)`` is true."""
        return self.derive(item for item in self if keep(item))

    @property
    def megabytes(self) -> float:
        """Total size in megabytes (unknown sizes count as 0)."""
        return sum(item.expected_size or 0 for item in self) / 1e6

    def download(self, dest, **options) -> list[Result]:
        """Same as ``eof.download(self, dest, **options)``."""
        return download(self, dest, **options)


def providers() -> list[ProviderInfo]:
    """All provider cards (name, access type, licence, last verified, notes)."""
    return all_providers()


def provider(name: str) -> ProviderInfo:
    """The card of one provider."""
    return get_provider(name)


def products(
    text: str = "",
    provider: str | None = None,
    *,
    live: bool | None = None,
    browse: bool | None = None,
    on_error: Callable[[ProviderInfo, Exception], None] | None = None,
) -> list[ProductMatch]:
    """Find the product names to use in :func:`search`.

    ``products()`` lists every alias of every provider; ``products("precipitation")`` keeps those
    whose name or description contains the word(s); ``products(provider="dwd")`` lists one
    provider (and, for file-tree providers, its top-level folders). With a ``provider`` and a
    ``text`` the live catalogue of the provider is searched too (``live=True`` does so for all
    providers, which needs the internet and, for some, credentials). Each result's ``product``
    is what you pass to :func:`search`. A provider whose live catalogue cannot be reached is
    skipped with a warning (or ``on_error(info, exception)`` if given).
    """
    return find_products(
        text, provider, live=live, browse=browse, make_backend=make_backend, on_error=on_error
    )


def search(
    provider: str,
    product: str = "",
    *,
    start=None,
    end=None,
    bbox=None,
    text: str = "",
    limit: int | None = None,
    params: Mapping[str, object] | None = None,
    **extra: object,
) -> Results:
    """Find items. ``start``/``end`` take ISO strings, dates or datetimes (``end`` is exclusive).

    ``bbox`` is (west, south, east, north) in degrees. Provider-specific options are keyword
    arguments (or a ``params`` dict), for example ``assets="B04,B08"`` or
    ``variable_id=["tas", "pr"]``; they are the ``--param`` options of the command line.
    """
    info = get_provider(provider)
    user_params = {
        key: param_text(value)
        for key, value in {**(params or {}), **extra}.items()
        if value is not None
    }
    backend = make_backend(info, user_params)
    query = Query(
        provider=info.name,
        product=info.products.get(product, product),
        start=parse_time(start) if start is not None else None,
        end=parse_time(end) if end is not None else None,
        bbox=tuple(float(value) for value in bbox) if bbox else None,
        text=text,
        limit=limit,
        params=user_params,
    )
    return Results(backend.search(query), info=info, backend=backend, query=query)


def download(
    results: Results,
    dest,
    *,
    workers: int | None = None,
    retries: int = 3,
    manifest=None,
    on_result: Callable[[Result], None] | None = None,
) -> list[Result]:
    """Download the items of a search into ``dest`` and write the manifest.

    Files are verified (size and checksum when the provider announces them), retried on errors,
    and never exceed the connections the service allows. The manifest goes to
    ``dest/manifest.json`` unless ``manifest`` is given. Failures do not raise: check
    ``result.status`` (``downloaded``, ``skipped`` or ``failed``) and ``result.error``.
    """
    if not isinstance(results, Results):
        raise TypeError(
            "Pass the result of eof.search() (or a slice or .where() of it), not a plain list"
        )
    if not results:
        return []
    dest = Path(dest)
    outcome = download_items(
        results.backend, list(results), dest, workers=workers, retries=retries, on_result=on_result
    )
    path = Path(manifest) if manifest else dest / "manifest.json"
    write_manifest(path, build_manifest(results.query, results.info, outcome))
    return outcome


def verify(manifest, root=None) -> list[str]:
    """Check downloaded files against a manifest; returns the problems (empty when all is well)."""
    manifest = Path(manifest)
    return verify_manifest(manifest, Path(root) if root else manifest.parent)


def collections(provider: str, text: str = "", **params: object) -> list[tuple[str, str]]:
    """List the collections or datasets a provider offers, optionally filtered by ``text``."""
    info = get_provider(provider)
    backend = make_backend(info, {k: param_text(v) for k, v in params.items()})
    lister = getattr(backend, "collections", None)
    if lister is None:
        raise NotImplementedError(f"The {info.backend} backend has no collection listing")
    return lister(text)


def login(provider: str) -> None:
    """Ask for the provider's credentials (hidden prompts) and save them in your user folder."""
    info = get_provider(provider)
    backend = make_backend(info, {})
    login_step = getattr(backend, "login", None)
    if login_step is None:
        raise NotImplementedError(f"{info.name} has no login step; see doctor({info.name!r})")
    login_step()


def doctor(provider: str, **params: object) -> bool:
    """Print what is needed to access a provider and whether it works; True when all is well."""
    info = get_provider(provider)
    backend = make_backend(info, {k: param_text(v) for k, v in params.items()})
    print(f"{info.name}: {info.title}")
    print(f"  access: {info.auth}; latency: {info.latency or 'not stated'}")
    print(f"  licence: {info.licence or 'not stated'}")
    check = getattr(backend, "doctor", None)
    if check is None:
        print("  no access diagnostics implemented for this backend yet")
        return True
    return bool(check())


def open_data(path, format: str | None = None, **options):
    """Open a downloaded file as an ``xarray.Dataset`` (NetCDF, GRIB, GeoTIFF, SEVIRI, ...)."""
    from eo_fetch.readers import open_data as reader

    return reader(path, format=format, **options)


def plot(
    source,
    output=None,
    *,
    variable: str | None = None,
    style: str | None = None,
    domain=None,
    resolution: float | None = None,
    bbox=None,
    title: str | None = None,
    **options,
) -> Path:
    """Draw a file or Dataset on a map with the shared styles; returns the image path."""
    from eo_fetch import plotting

    if output is None:
        if not isinstance(source, str | Path):
            raise ValueError("Give output=... when plotting a Dataset")
        output = Path("plots") / (Path(source).stem[:60] + ".png")
    plotting.plot(
        source,
        Path(output),
        variable=variable,
        style=style,
        domain=domain,
        resolution=resolution,
        bbox=tuple(bbox) if bbox else None,
        title=title,
        **options,
    )
    return Path(output)


def convert(source, output, *, resolution: float | None = None, bbox=None, **options) -> Path:
    """Write a readable file as NetCDF (``.nc``) or Zarr (``.zarr``), optionally on lat/lon."""
    from eo_fetch import bridge

    return bridge.convert(
        source, Path(output), resolution=resolution, bbox=tuple(bbox) if bbox else None, **options
    )


def to_earthkit(source, variable: str | None = None, resolution=None, bbox=None, **options):
    """An earthkit-data object for a file, ready for earthkit-plots, -regrid or -transforms."""
    from eo_fetch import bridge

    return bridge.to_earthkit(source, variable, resolution, bbox, **options)
