"""Provider cards: importing this package registers every provider."""

from eo_fetch.catalog import dwd, eumetsat, nasa, noaa, stac

__all__ = ["dwd", "eumetsat", "nasa", "noaa", "stac"]
