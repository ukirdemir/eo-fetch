"""eo-fetch: one search-and-download interface for Earth-observation and climate data.

import eo_fetch as eof
"""

__version__ = "1.0.0"

from eo_fetch.api import (
    Results,
    collections,
    convert,
    doctor,
    download,
    login,
    plot,
    products,
    provider,
    providers,
    search,
    to_earthkit,
    verify,
)
from eo_fetch.api import open_data as open
from eo_fetch.discovery import ProductMatch
from eo_fetch.downloader import Result
from eo_fetch.models import Item, Query

__all__ = [
    "Item",
    "ProductMatch",
    "Query",
    "Result",
    "Results",
    "__version__",
    "collections",
    "convert",
    "doctor",
    "download",
    "login",
    "open",
    "plot",
    "products",
    "provider",
    "providers",
    "search",
    "to_earthkit",
    "verify",
]
