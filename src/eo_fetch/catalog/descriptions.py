"""One-line descriptions of the product aliases of every provider card.

Keys are ``"provider/alias"``. A test checks that every alias has a description, so new aliases
must be added here.
"""

from __future__ import annotations

GOES_SATELLITES = {"16": "GOES-16 (archive)", "18": "GOES-18 (West)", "19": "GOES-19 (East)"}

GOES_PRODUCTS = {
    "cmip-conus": "ABI cloud and moisture imagery, one band per file, continental US",
    "cmip-fulldisk": "ABI cloud and moisture imagery, one band per file, full disk",
    "cmip-mesoscale": "ABI cloud and moisture imagery, one band per file, mesoscale sector",
    "mcmip-conus": "ABI cloud and moisture imagery, all 16 bands in one file, continental US",
    "radiance-conus": "ABI level-1b radiances, continental US",
    "radiance-fulldisk": "ABI level-1b radiances, full disk",
    "lightning": "GLM lightning events, groups and flashes (level 2)",
}

PRODUCT_NOTES: dict[str, str] = {
    # DWD open data
    "dwd/radolan": "RADOLAN radar rain composites, all variants, Germany",
    "dwd/radolan-yw": "RADOLAN YW: radar rain rate every 5 minutes, Germany",
    "dwd/radar-composite": "Radar reflectivity composites and derived products, Germany",
    "dwd/radvor": "RADVOR radar-based precipitation nowcasts",
    "dwd/radar-sites": "Single-site radar data",
    "dwd/satellite": "Satellite-derived products (for example surface radiation, clouds)",
    "dwd/icon": "ICON global model output (icosahedral grid)",
    "dwd/icon-eu": "ICON-EU nest on a regular latitude/longitude grid, Europe",
    "dwd/icon-d2": "ICON-D2 convection-permitting model, Germany and surroundings",
    "dwd/icon-d2-grib": "ICON-D2 output as GRIB files",
    "dwd/icon-eps": "ICON ensemble forecasts",
    "dwd/cdc-grids-germany": "Climate Data Center gridded climate data, Germany",
    "dwd/cdc-grids-europe": "Climate Data Center gridded climate data, Europe",
    "dwd/cdc-grids-5min-radolan": "5-minute radar precipitation grids, Germany (historical)",
    "dwd/cdc-observations-germany": "Station observations, Germany (zip files; no reader yet)",
    "dwd/cdc-air-temperature-hourly-recent": "Hourly station air temperature, recent (zips)",
    "dwd/cdc-regional-averages": "Regional climate averages for Germany (text tables)",
    # EUMETSAT Data Store
    "eumetsat/seviri": "Meteosat SEVIRI level 1.5, full disc every 15 minutes (0 degrees)",
    "eumetsat/seviri-iodc": "Meteosat SEVIRI level 1.5 imagery, Indian Ocean service (IODC)",
    "eumetsat/seviri-rss": "Meteosat SEVIRI rapid scan service, every 5 minutes, Europe",
    "eumetsat/seviri-cloud-mask": "SEVIRI cloud mask",
    "eumetsat/seviri-cloud-top-height": "SEVIRI cloud top height",
    "eumetsat/fci-normal": "MTG FCI level 1c, normal resolution (FDHSI)",
    "eumetsat/fci-high": "MTG FCI level 1c, high resolution (HRFI)",
    "eumetsat/fci-cloud-mask": "MTG FCI cloud mask",
    "eumetsat/mtg-precip-rate": "MTG precipitation product",
    "eumetsat/mtg-lightning-flashes": "MTG Lightning Imager flashes",
    "eumetsat/metop-iasi-l1c": "Metop IASI level 1c spectra (large files)",
    "eumetsat/metop-ascat-soil-moisture-25km": "ASCAT soil moisture, 25 km (BUFR; no reader)",
    "eumetsat/cmsaf-sarah3": "CM SAF SARAH-3 surface solar radiation from Meteosat",
    "eumetsat/cmsaf-girafe-rainfall": "CM SAF GIRAFE gridded rainfall",
    # NASA Earthdata
    "nasa/imerg-late-daily": "GPM IMERG Late Run, daily precipitation, 0.1 degree",
    "nasa/imerg-late-halfhourly": "GPM IMERG Late Run, precipitation every 30 minutes",
    "nasa/imerg-final-daily": "GPM IMERG Final Run, daily precipitation, gauge-adjusted",
    "nasa/imerg-final-halfhourly": "GPM IMERG Final Run, precipitation every 30 minutes",
    "nasa/imerg-final-monthly": "GPM IMERG Final Run, monthly precipitation",
    "nasa/omi-no2-daily": "Aura OMI nitrogen dioxide, daily 0.25 degree grid",
    "nasa/smap-soil-moisture-daily": "SMAP level 3 daily soil moisture (radiometer)",
    "nasa/merra2-surface-hourly": "MERRA-2 hourly single-level fields (temperature, wind, ...)",
    # STAC catalogues
    "planetary-computer/sentinel-2": "Sentinel-2 level 2A surface reflectance",
    "planetary-computer/sentinel-1-rtc": "Sentinel-1 radiometrically terrain-corrected radar",
    "planetary-computer/landsat": "Landsat collection 2 level 2 surface reflectance",
    "planetary-computer/land-cover-worldcover": "ESA WorldCover 10 m global land cover",
    "planetary-computer/land-use-lulc": "Annual 10 m land use / land cover (Impact Observatory)",
    "planetary-computer/era5": "ERA5 reanalysis (AWS public copy)",
    "planetary-computer/terraclimate": "TerraClimate monthly climate and water balance",
    "planetary-computer/dem-nasadem": "NASADEM 30 m elevation",
    "earth-search/sentinel-2": "Sentinel-2 level 2A surface reflectance (cloud-optimised files)",
    "earth-search/sentinel-1": "Sentinel-1 GRD radar backscatter",
    "earth-search/dem-30m": "Copernicus DEM, 30 m elevation",
    "earth-search/dem-90m": "Copernicus DEM, 90 m elevation",
    "cdse/sentinel-2": "Sentinel-2 level 2A surface reflectance (needs S3 keys)",
    "cdse/sentinel-1": "Sentinel-1 GRD radar backscatter (needs S3 keys)",
    # Forecasts and reanalyses
    "ecmwf-open-data/ifs-hres": "ECMWF IFS high-resolution forecast (0.25 degree, 10 days)",
    "ecmwf-open-data/ifs-ensemble": "ECMWF IFS ensemble forecast (51 members)",
    "cds/era5-single-levels": "ERA5 hourly reanalysis on single levels (2 m temperature, ...)",
    "cds/era5-pressure-levels": "ERA5 hourly reanalysis on pressure levels",
    "cds/era5-land": "ERA5-Land hourly land reanalysis, 9 km",
    "copernicus-marine/sst-l4-nrt": "Daily gap-free sea surface temperature (OSTIA, NRT)",
    "esgf/cmip3": "CMIP3 climate-model output (old; may no longer be served)",
    "esgf/cmip5": "CMIP5 climate-model output (tested; needs --param indices=all)",
    "esgf/cmip6": "CMIP6 climate-model output (tested; give facets with --param)",
    "esgf/cmip7": "CMIP7 climate-model output (give facets with --param)",
    "esgf/cordex-cmip6": "CORDEX-CMIP6 regional climate downscaling (give facets with --param)",
    "esgf/input4mips": "input4MIPs model forcing datasets",
    "esgf/obs4mips": "obs4MIPs observations formatted for model comparison",
    # NOAA open data on AWS
    "noaa/mrms": "MRMS multi-radar precipitation estimates, United States",
    "noaa/gfs": "GFS global forecast model (GRIB)",
    "noaa/gefs": "GEFS global ensemble forecast",
    "noaa/hrrr": "HRRR high-resolution rapid refresh forecast, United States",
    "noaa/rap": "RAP rapid refresh forecast, North America (GRIB/BUFR)",
    "noaa/nbm": "National Blend of Models forecasts",
    "noaa/ghcn-daily": "GHCN daily station observations",
    "noaa/persiann-cdr": "PERSIANN-CDR precipitation climate data record",
    "noaa/nodd-kerchunk": "Kerchunk reference files for cloud-optimised NOAA model data",
    "noaa/viirs-noaa20": "NOAA-20 VIIRS products",
    "noaa/jpss": "JPSS satellite products",
    "noaa/nexrad-level2": "NEXRAD weather radar level II, by date and site (no reader yet)",
    "noaa/nexrad-level2-chunks": "NEXRAD level II real-time chunks",
}

for _number, _label in GOES_SATELLITES.items():
    for _alias, _text in GOES_PRODUCTS.items():
        PRODUCT_NOTES[f"noaa/goes{_number}-{_alias}"] = f"{_label}: {_text}"


def describe_alias(provider: str, alias: str) -> str:
    """The one-line description of a product alias, or an empty string."""
    return PRODUCT_NOTES.get(f"{provider}/{alias}", "")
