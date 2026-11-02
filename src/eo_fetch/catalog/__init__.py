"""Provider cards: importing this package registers every provider."""

from eo_fetch.catalog import eumetsat, noaa

__all__ = ["eumetsat", "noaa"]
