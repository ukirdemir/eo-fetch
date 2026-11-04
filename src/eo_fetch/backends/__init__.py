"""Backends and the registry that builds them by name."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping

from eo_fetch.backends.base import Backend
from eo_fetch.backends.cds import CdsBackend
from eo_fetch.backends.ecmwf import EcmwfOpenDataBackend
from eo_fetch.backends.eumetsat import EumetsatBackend
from eo_fetch.backends.http_index import HttpIndexBackend
from eo_fetch.backends.local import LocalBackend
from eo_fetch.backends.nasa import NasaBackend
from eo_fetch.backends.s3 import S3Backend
from eo_fetch.backends.stac import StacBackend

# Backends import their third-party library only when first used, so listing is always cheap.
BACKENDS: dict[str, Callable[..., Backend]] = {
    "local": LocalBackend,
    "eumetsat": EumetsatBackend,
    "s3": S3Backend,
    "http-index": HttpIndexBackend,
    "nasa": NasaBackend,
    "stac": StacBackend,
    "ecmwf-opendata": EcmwfOpenDataBackend,
    "cds": CdsBackend,
}


def backend_factory(name: str) -> Callable[..., Backend]:
    try:
        return BACKENDS[name]
    except KeyError:
        known = ", ".join(sorted(BACKENDS))
        raise KeyError(f"Unknown backend {name!r}. Available: {known}") from None


def param_names(name: str) -> tuple[set[str], set[str]]:
    """Return (constructor parameters, search parameters) a backend accepts."""
    factory = backend_factory(name)
    return set(inspect.signature(factory).parameters), set(getattr(factory, "query_params", ()))


def get_backend(name: str, params: Mapping[str, str] | None = None) -> Backend:
    """Build a backend by name; only the parameters its constructor accepts are passed on."""
    accepted, _ = param_names(name)
    return backend_factory(name)(**{k: v for k, v in (params or {}).items() if k in accepted})


__all__ = [
    "BACKENDS",
    "Backend",
    "CdsBackend",
    "EcmwfOpenDataBackend",
    "EumetsatBackend",
    "HttpIndexBackend",
    "LocalBackend",
    "NasaBackend",
    "S3Backend",
    "StacBackend",
    "backend_factory",
    "get_backend",
    "param_names",
]
