"""The provider registry: what each source is, how to access it, and under which terms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderInfo:
    """A named data source mapped to a backend, with its access and licence notes.

    ``products`` maps readable aliases to the backend's own product identifiers. ``verified``
    states when the adapter was last tested on real downloads (empty means not yet).
    """

    name: str
    backend: str
    title: str
    auth: str = "none"  # "none", "account" or "licence"
    licence: str = ""
    attribution: str = ""
    latency: str = ""
    notes: str = ""
    verified: str = ""
    backend_params: Mapping[str, str] = field(default_factory=dict)
    products: Mapping[str, str] = field(default_factory=dict)


PROVIDERS: dict[str, ProviderInfo] = {}
_catalog_loaded = False


def register(info: ProviderInfo) -> ProviderInfo:
    """Add a provider to the registry (replacing one of the same name)."""
    PROVIDERS[info.name] = info
    return info


def load_catalog() -> None:
    """Import the catalog modules once; each registers its providers."""
    global _catalog_loaded
    if not _catalog_loaded:
        _catalog_loaded = True
        import eo_fetch.catalog  # noqa: F401


def all_providers() -> list[ProviderInfo]:
    load_catalog()
    return sorted(PROVIDERS.values(), key=lambda info: info.name)


def get_provider(name: str) -> ProviderInfo:
    load_catalog()
    try:
        return PROVIDERS[name]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS)) or "none registered"
        raise KeyError(f"Unknown provider {name!r}. Available: {known}") from None


register(
    ProviderInfo(
        name="local",
        backend="local",
        title="Files in a local or network folder (pass --param root=DIR)",
        notes="Used for tests and for staging data; the query text is a glob pattern.",
        verified="tests",
    )
)
