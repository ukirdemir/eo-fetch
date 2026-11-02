"""Backends and the registry that builds them by name."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from eo_fetch.backends.base import Backend
from eo_fetch.backends.eumetsat import EumetsatBackend
from eo_fetch.backends.local import LocalBackend

# Backends import their third-party library only when first used, so listing is always cheap.
BACKENDS: dict[str, Callable[..., Backend]] = {
    "local": LocalBackend,
    "eumetsat": EumetsatBackend,
}


def get_backend(name: str, params: Mapping[str, str] | None = None) -> Backend:
    """Build a backend by name; ``params`` are passed as keyword arguments."""
    try:
        factory = BACKENDS[name]
    except KeyError:
        known = ", ".join(sorted(BACKENDS))
        raise KeyError(f"Unknown backend {name!r}. Available: {known}") from None
    return factory(**dict(params or {}))


__all__ = ["BACKENDS", "Backend", "EumetsatBackend", "LocalBackend", "get_backend"]
