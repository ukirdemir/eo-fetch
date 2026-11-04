"""Provider cards: importing this package registers every provider."""

from eo_fetch.catalog import copernicus_ecmwf, dwd, eumetsat, nasa, noaa, stac

__all__ = ["copernicus_ecmwf", "dwd", "eumetsat", "nasa", "noaa", "stac"]
