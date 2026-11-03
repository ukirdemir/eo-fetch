"""Provider cards: importing this package registers every provider."""

from eo_fetch.catalog import dwd, eumetsat, noaa

__all__ = ["dwd", "eumetsat", "noaa"]
