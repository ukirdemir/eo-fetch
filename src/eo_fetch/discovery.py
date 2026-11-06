"""Find product names: the aliases of the provider cards and, optionally, live catalogues."""

from __future__ import annotations

import difflib
import warnings
from collections.abc import Callable
from dataclasses import dataclass

from eo_fetch.catalog.descriptions import describe_alias
from eo_fetch.models import Query
from eo_fetch.registry import ProviderInfo, all_providers, get_provider


@dataclass(frozen=True)
class ProductMatch:
    """One product a user can pass as ``--product``.

    ``source`` is ``"alias"`` (a name from the provider card), ``"catalogue"`` (found in the
    provider's live catalogue) or ``"folder"`` (a top-level folder of a file tree).
    ``identifier`` is the provider's own id behind an alias.
    """

    provider: str
    product: str
    description: str
    source: str
    identifier: str = ""


def alias_matches(info: ProviderInfo, wanted: list[str]) -> list[ProductMatch]:
    """Aliases of one provider whose name, id or description contain every wanted word."""
    found = []
    for alias, identifier in sorted(info.products.items()):
        note = describe_alias(info.name, alias)
        haystack = " ".join((info.name, alias, identifier, note)).lower()
        if all(word in haystack for word in wanted):
            found.append(ProductMatch(info.name, alias, note, "alias", identifier))
    return found


def catalogue_matches(info: ProviderInfo, text: str, backend) -> list[ProductMatch]:
    """Collections of the provider's live catalogue that match ``text`` (and are not aliases)."""
    lister = getattr(backend, "collections", None)
    if lister is None or not text:
        return []
    known = set(info.products.values())
    return [
        ProductMatch(info.name, identifier, title, "catalogue")
        for identifier, title in lister(text)
        if identifier not in known
    ]


def folder_matches(info: ProviderInfo, backend) -> list[ProductMatch]:
    """Top-level folders of a file-tree provider (such as DWD open data)."""
    if info.backend != "http-index":
        return []
    backend.search(Query(provider=info.name, product="", limit=1))
    folders = getattr(backend, "folders_seen", [])
    return [ProductMatch(info.name, folder, "", "folder") for folder in folders]


def find_products(
    text: str = "",
    provider: str | None = None,
    *,
    live: bool | None = None,
    browse: bool | None = None,
    make_backend: Callable[[ProviderInfo, dict], object],
    on_error: Callable[[ProviderInfo, Exception], None] | None = None,
) -> list[ProductMatch]:
    """Products matching ``text`` (all words must occur), of one provider or of all.

    ``live`` also asks the live catalogues (network; default: only when ``provider`` is given).
    ``browse`` lists the top-level folders of a file-tree provider (default: when ``provider``
    is given and ``text`` is empty).
    """
    wanted = text.lower().split()
    infos = [get_provider(provider)] if provider else all_providers()
    if live is None:
        live = provider is not None
    if browse is None:
        browse = provider is not None and not text
    report = on_error or (
        lambda info, error: warnings.warn(
            f"{info.name}: live search skipped ({type(error).__name__}: {error})", stacklevel=2
        )
    )
    found: list[ProductMatch] = []
    for info in infos:
        found += alias_matches(info, wanted)
        wants_catalogue = live and bool(text)
        if not (wants_catalogue or browse):
            continue
        try:
            backend = make_backend(info, {})
            if wants_catalogue:
                found += catalogue_matches(info, text, backend)
            if browse:
                found += folder_matches(info, backend)
        except Exception as error:
            report(info, error)
    return found


def suggest(info: ProviderInfo, product: str, count: int = 3) -> list[str]:
    """Aliases of a provider that look like a product name the user may have mistyped."""
    if not product or product in info.products or product in info.products.values():
        return []
    return difflib.get_close_matches(product, list(info.products), n=count, cutoff=0.5)
