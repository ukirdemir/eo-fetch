# eo-fetch

One search-and-download interface, with reproducible manifests, on top of the libraries that already talk to Earth-observation and climate data providers.

Status: early development (phase 0). The core, downloader, manifest and CLI work and are tested offline; the real providers are added one by one, and each provider card will state what was tested on real downloads.

## What it does

- **One query model** for every provider: product, time range, area, keyword.
- **Resumable, verified downloads**: files are written under a temporary name, checked for size and checksum when the provider announces them, retried with back-off, and never exceed the number of connections a service allows.
- **A manifest** for every download run: what was fetched, from where, when, with sizes, SHA-256 checksums and the licence and attribution text of the provider. `eo-fetch verify` checks the files against it later.
- **A provider registry** with access type (none, account, licence), latency, licence and "last verified" notes.
- Backends wrap existing libraries (`eumdac`, `earthaccess`, `pystac-client`, `herbie`, `wetterdienst`, `earthkit-data`, `copernicusmarine`, `esgpull`, `cdsapi`) as optional extras; `eo-fetch` does not replace them.

## Install and try

Python 3.12 or newer (the earthkit packages have no wheels for 3.14 yet).

```
pip install -e ".[dev]"
pytest
eo-fetch providers
eo-fetch search --provider local --param root=. --text "*.py"
eo-fetch download --provider local --param root=src --text "*.py" --dest downloads --dry-run
```

## Planned providers

EUMETSAT Data Store (all collections), NOAA open data on AWS, DWD open data (whole tree), NASA Earthdata (the whole CMR catalogue), STAC catalogues (Planetary Computer, AWS Earth Search, Copernicus Data Space), Copernicus Climate Data Store and ECMWF open data (via earthkit-data), Copernicus Marine, ESGF. A common plotting style built on earthkit-plots follows after the providers. Version 2: CHIRPS and other precipitation products, river flow, soil moisture, land use.

## Development

```
ruff check .
ruff format --check .
pytest -m "not network and not account"
```

Tests that need the internet or a provider account are marked `network` or `account` and are skipped in CI.
