# eo-fetch

One search-and-download interface, with reproducible manifests, on top of the libraries that already talk to Earth-observation and climate data providers, plus readers and map plots for what you download.

Status: early development. Three providers are tested on real downloads (EUMETSAT Data Store, NOAA open data on AWS, DWD open data); NASA Earthdata, STAC catalogues, Copernicus and ECMWF follow. Each provider card states when it was last verified.

## What it does

- **One query model** for every provider: product, time range, area, keyword.
- **Resumable, verified downloads**: files are written under a temporary name, checked for size and checksum when the provider announces them, retried with back-off, and never exceed the number of connections a service allows.
- **A manifest** for every download run: what was fetched, from where, when, with sizes, SHA-256 checksums and the licence and attribution text of the provider. `eo-fetch verify` checks the files against it later.
- **A provider registry** with access type (none, account, licence), latency, licence and "last verified" notes.
- **Readers**: `eo-fetch open` and `eo_fetch.readers.open_data` open downloaded files as xarray datasets: NetCDF, HDF5, Zarr, GRIB, GeoTIFF/ESRI ASCII, gzip/bzip2/zip containers, and dedicated readers for MSG SEVIRI (native and level-2 GRIB), MTG FCI level-1c, GOES ABI and DWD radar composites (ODIM HDF5).
- **Maps**: `eo-fetch plot` draws a file with earthkit-plots in one shared style registry (`eo-fetch styles`); projected data (radar, geostationary) is regridded to latitude/longitude first. `eo-fetch convert` writes NetCDF or Zarr, and `eo_fetch.bridge.to_earthkit` hands data to earthkit.
- Backends wrap existing libraries (`eumdac`, `earthaccess`, `pystac-client`, `herbie`, `wetterdienst`, `earthkit-data`, `copernicusmarine`, `intake-esgf`, `cdsapi`) as optional extras; `eo-fetch` does not replace them.

## Install and try

Python 3.12 or newer (the earthkit packages have no wheels for 3.14 yet).

```
pip install -e ".[dev,readers,satellite,earthkit,eumetsat,noaa]"
pytest
eo-fetch providers
eo-fetch search --provider dwd --product radolan-yw --limit 3
eo-fetch download --provider dwd --product radolan-yw --limit 2 --dest data/dwd
eo-fetch verify data/dwd/manifest.json --root data/dwd
eo-fetch open data/dwd/raa01-yw_10000-2611011130-dwd---bin.hdf5
eo-fetch plot data/dwd/raa01-yw_10000-2611011130-dwd---bin.hdf5 --bbox 5 47 16 55.5
```

## Credentials

Providers with accounts have a one-time `eo-fetch login --provider NAME` (hidden prompt, saved in your user folder as a plain-text file; delete the file to log out), and `eo-fetch doctor --provider NAME` tells you what is missing. You can also set the environment variables or write the file yourself. eo-fetch never stores credentials anywhere else and never sends them to any service except the provider.

| Provider | `login` writes | Or use |
| --- | --- | --- |
| `nasa` (Earthdata) | `~/.netrc` | `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`, or `EARTHDATA_TOKEN`; approve the provider's application once at urs.earthdata.nasa.gov |
| `eumetsat` | `~/.eumdac/credentials` | `EUMETSAT_KEY` and `EUMETSAT_SECRET`; a licence per collection |
| `cds` (ERA5) | `~/.cdsapirc` | `CDSAPI_URL` and `CDSAPI_KEY`; accept each dataset's licence on its page |
| `copernicus-marine` | `~/.copernicusmarine/.copernicusmarine-credentials` (written by the toolbox) | `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD` |
| `cdse` | none | `CDSE_S3_KEY` and `CDSE_S3_SECRET` from the Copernicus Data Space S3 key manager |
| `dwd`, `noaa`, `earth-search`, `planetary-computer`, `ecmwf-open-data`, `esgf` | none needed | |

## Which files can be opened?

`eo-fetch check-readers` downloads the smallest recent file of every product alias of every provider and tries to open it, and prints ok, no reader, fail or skip for each. In the last full run: all GOES-18/19 products, SEVIRI (L1.5, IODC, RSS, cloud mask, cloud top height), FCI level 1c and cloud mask, MTG precipitation and lightning, CM SAF products, DWD radar composites, ICON-EU, DWD satellite radiation and NOAA GFS GRIB opened. Not readable yet: BUFR (ASCAT, RAP), DWD station zips and radar `.tar` composites, NEXRAD, and ICON icosahedral grids open only as a flat list of values (they need DWD's grid files for coordinates). Unknown formats raise a clear "no reader" error that lists the supported formats.

## Planned providers

EUMETSAT Data Store (all collections), NOAA open data on AWS, DWD open data (whole tree), NASA Earthdata (the whole CMR catalogue), STAC catalogues (Planetary Computer, AWS Earth Search, Copernicus Data Space), Copernicus Climate Data Store and ECMWF open data (via earthkit-data), Copernicus Marine, ESGF. Version 2: CHIRPS and other precipitation products, river flow, soil moisture, land use.

## Development

```
ruff check .
ruff format --check .
pytest -m "not network and not account"
```

Tests that need the internet or a provider account are marked `network` or `account` and are skipped in CI.
