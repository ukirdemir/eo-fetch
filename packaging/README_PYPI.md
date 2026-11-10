# eo-fetch

One search-and-download interface, with verified downloads and reproducible manifests, on top of the libraries that already talk to Earth-observation and climate data providers. Readers and map plots for what you download are included.

```python
import eo_fetch as eof

found = eof.search("dwd", "radolan-yw", limit=2)  # same query model for every provider
eof.download(found, "data/dwd")  # verified files + manifest.json
ds = eof.open(f"data/dwd/{found[0].filename}")  # xarray Dataset
eof.plot(ds, "plots/radar.png")  # map in the shared style registry
```

Every provider below was tested on a real download; each provider card states the date it was last verified (`eof.providers()`).

## What it does

- **One query model** for every provider: product, time range, area, keyword, plus provider-specific options.
- **Verified, resumable downloads**: files are written under a temporary name, checked for size and checksum when the provider announces them, retried with back-off, and never exceed the number of connections a service allows.
- **A manifest** for every download run: what was fetched, from where, when, sizes, SHA-256 checksums, and the provider's licence and attribution. `eof.verify` checks the files against it later.
- **A provider registry** with access type (none, account, licence), latency, licence, attribution and "last verified" date.
- **Readers**: NetCDF, HDF5, Zarr, GRIB, GeoTIFF/JPEG 2000/ESRI ASCII, gzip/bzip2/zip containers, and dedicated readers for MSG SEVIRI (native and level-2 GRIB), MTG FCI level-1c, GOES ABI and DWD radar composites.
- **Maps**: one style registry on top of earthkit-plots; projected data (radar, geostationary) is regridded to latitude/longitude first. NetCDF/Zarr conversion and an earthkit-data bridge.
- Backends wrap existing libraries (`eumdac`, `earthaccess`, `pystac-client`, `earthkit-data`, `copernicusmarine`, `intake-esgf`, `cdsapi`, `ecmwf-opendata`). eo-fetch does not replace them.

## Install

Python 3.12 or 3.13 (the earthkit packages have no wheels for 3.14 yet).

```
pip install eo-fetch-api
```

One install includes every provider, the readers and the plots. The package is imported as `eo_fetch`: `import eo_fetch as eof`.

## Python API

```python
import eo_fetch as eof
```

Options that are specific to a provider are keyword arguments.

### Find product names

```python
for match in eof.products("precipitation"):  # aliases of all providers
    print(match.provider, match.product, "-", match.description)
eof.products(provider="dwd")  # one provider (+ top-level folders)
eof.products("soil moisture", "nasa")  # with a provider: live catalogue too
```

`eof.products(text="", provider=None, *, live=None, browse=None)` returns `eof.ProductMatch` objects (`provider`, `product`, `description`, `source`); pass `match.product` to `eof.search`.

### Search

```python
found = eof.search(
    "nasa",
    "imerg-late-daily",
    start="2026-10-01",
    end="2026-10-03",  # ISO strings, dates or datetimes (end exclusive)
    bbox=(5, 47, 16, 55),  # west, south, east, north
)
print(len(found), f"{found.megabytes:.1f} MB")
for item in found:
    print(item.time, item.key, item.size)
```

`eof.search(provider, product="", *, start, end, bbox, text, limit, params, **options)` returns `eof.Results`, a normal list of `eof.Item` that also remembers how to download itself. Provider options go in as keywords or in a `params` dict; lists become comma-separated values:

```python
eof.search(
    "cdse",
    "sentinel-2",
    start="2026-10-28",
    end="2026-10-30",
    bbox=(8.5, 53.4, 9.5, 53.8),
    assets=["B04_60m", "SCL_60m"],
    limit=2,
)
eof.search(
    "esgf",
    "CMIP6",
    variable_id="tas",
    experiment_id="historical",
    source_id="CanESM5",
    member_id="r1i1p1f1",
    table_id="Amon",
)
eof.search(
    "cds",
    "era5-single-levels",
    start="2026-01-01",
    end="2026-02-01",
    variable="2m_temperature",
    bbox=(5, 47, 16, 55),
)
```

An unknown option raises `ValueError` with the accepted names. Filter or slice the results freely (`found[:3]`, `found.where(lambda item: item.size < 5e6)`); they keep working with `eof.download`.

### Download and verify

```python
results = eof.download(found, "data/imerg")  # also writes data/imerg/manifest.json
failed = [r for r in results if r.status == "failed"]  # downloaded | skipped | failed
problems = eof.verify("data/imerg/manifest.json")  # [] when every file matches
```

`eof.download(results, dest, *, workers=None, retries=3, manifest=None, on_result=None)` returns a list of `eof.Result` (`item`, `path`, `status`, `size`, `sha256`, `seconds`, `error`). Failures do not raise. Files that already exist with the right size and checksum are skipped, so the same call resumes an interrupted run. `on_result` is called as each file finishes (for progress output).

### Open, plot, convert

```python
ds = eof.open(results[0].path)  # path of the first downloaded file
path = eof.plot(ds, "plots/imerg.png", bbox=(5, 47, 16, 55), style="precip-daily")
eof.convert("data/era5/era5.grib", "data/era5/era5.nc")  # or .zarr
ekd = eof.to_earthkit("data/era5/era5.grib")  # earthkit-data object
```

`eof.open(path, format=None, **options)` returns an `xarray.Dataset`; the format is detected from the name and content (see below). `eof.plot(source, output=None, *, variable, style, domain, resolution, bbox, title)` accepts a file or a Dataset and returns the image path. The style names are the keys of `eo_fetch.styles.STYLES`.

### Providers, credentials, diagnostics

```python
for info in eof.providers():  # ProviderInfo cards
    print(info.name, info.auth, info.verified)
eof.provider("cds").notes  # how to use the provider, options, limits
eof.collections("copernicus-marine", "sea surface temperature")
eof.login("cds")  # hidden prompts; saves to your user folder
eof.doctor("nasa")  # prints what is missing; True when all is well
```

Lower-level pieces (`eo_fetch.backends`, `eo_fetch.readers`, `eo_fetch.regrid`) are importable too and are what the functions above are built on. To add a provider, implement the `Backend` protocol (`search(query)`, `fetch(item, target)`, `max_connections`) and register a `ProviderInfo` card.

## Providers

`eof.providers()` always shows the current list and verification dates.

| Provider | What | Access |
| --- | --- | --- |
| `eumetsat` | EUMETSAT Data Store: Meteosat, MTG, Metop, Sentinel-3/5P/6, CM SAF (all collections) | licence per collection |
| `noaa` | GOES-R (16, 18, 19) and other public NOAA buckets on AWS | none |
| `dwd` | DWD open data tree: radar, ICON models, climate data centre | none |
| `nasa` | every collection of NASA's CMR (IMERG, MERRA-2, OMI, SMAP, ...) | free Earthdata account |
| `planetary-computer`, `earth-search` | STAC catalogues: Sentinel, Landsat, land cover, climate | none |
| `cdse` | Copernicus Data Space (Sentinel) via STAC and S3 | free account + S3 keys |
| `ecmwf-open-data` | IFS and ensemble forecasts by parameter and lead time | none |
| `cds` | ERA5, ERA5-Land and other Climate Data Store datasets | free account, licence per dataset |
| `copernicus-marine` | ocean physics, biogeochemistry, sea ice, waves | free account |
| `esgf` | CMIP climate-model output (CMIP5 and CMIP6 tested; CMIP3/7, CORDEX-CMIP6, obs4MIPs as far as the indices serve them) | none |

Each card (`eof.provider(name)`) lists licence, attribution, latency and the options of that provider. Respect the licence and attribution when you publish results; the manifest records both.

## Credentials

Providers with accounts have a one-time `eof.login("NAME")` (hidden prompts; the login is saved as a plain-text file in your user folder, and deleting the file logs you out). `eof.doctor("NAME")` tells you what is missing. You can also set the environment variables, which take priority, or write the file yourself. eo-fetch never stores credentials anywhere else, never writes them into manifests or download folders, and sends them only to the provider.

| Provider | `eof.login` writes | Or use |
| --- | --- | --- |
| `nasa` (Earthdata) | `~/.netrc` | `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`, or `EARTHDATA_TOKEN`; approve the provider's application once at urs.earthdata.nasa.gov |
| `eumetsat` | `~/.eumdac/credentials` | `EUMETSAT_KEY` and `EUMETSAT_SECRET`; a licence per collection |
| `cds` (ERA5) | `~/.cdsapirc` | `CDSAPI_URL` and `CDSAPI_KEY`; accept each dataset's licence on its page |
| `copernicus-marine` | `~/.copernicusmarine/.copernicusmarine-credentials` (written by the toolbox) | `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD` |
| `cdse` | `~/.eo-fetch/cdse` (`key,secret`) | `CDSE_S3_KEY` and `CDSE_S3_SECRET` from the Copernicus Data Space S3 key manager (searching needs no keys) |
| `dwd`, `noaa`, `earth-search`, `planetary-computer`, `ecmwf-open-data`, `esgf` | none needed | |

## Which files can be opened?

`eof.open` detects the format from the file name and content. In the last full test, which tried the smallest recent file of every product alias of every provider, these opened: all GOES-18/19 products, SEVIRI (L1.5, IODC, RSS, cloud mask, cloud top height), FCI level 1c and cloud mask, MTG precipitation and lightning, CM SAF products, DWD radar composites, ICON-EU, DWD satellite radiation and NOAA GFS GRIB. Sentinel-2 JPEG 2000, ERA5 GRIB/NetCDF, ECMWF open data, Copernicus Marine and CMIP6 NetCDF were opened in the provider tests. Unknown formats raise a clear "no reader" error that lists the supported formats.

Known limits:

- Not readable yet: BUFR (ASCAT, RAP), DWD station zips and radar `.tar` composites, NEXRAD.
- ICON icosahedral grids open only as a flat list of values (they need DWD's grid files for coordinates).
- OMI and SMAP HDF5 files open but are not plotted (2-D latitude/longitude arrays).
- Plots draw the first entry of extra dimensions (time, level, band). Categorical rasters such as Sentinel-2 `SCL` have no dedicated style yet.
- CMIP6 searches may warn about a publishing error in the new STAC indices of ESGF; the warning is from `intake-esgf`. Switch those indices off with `indices="-discovery.east.esgf.io,-discovery.west.esgf.io"` in `eof.search`. Older projects (CMIP5, CMIP3) are only in the legacy indices: add `indices="all"`. Legacy nodes that are offline are reported in one short note; skip one with a leading minus, for example `indices="all,-esgf-node.ipsl.upmc.fr"`.
- On Windows, paths are limited to 260 characters; use a short destination folder. A harmless `Error in sys.excepthook` message can appear at exit after reading GeoTIFF/JPEG 2000 files.
