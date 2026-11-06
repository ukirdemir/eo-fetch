# Changelog

All notable changes to eo-fetch. The format follows [Keep a Changelog](https://keepachangelog.com), and versions follow [Semantic Versioning](https://semver.org).

## 1.0.0 - 2026-11-06

First public release.

### Added

- One query model and command line (`eo-fetch`) and Python API (`import eo_fetch as eof`) for searching and downloading: `search`, `download`, `verify`, `products`, `collections`, `doctor`, `login`, `open`, `plot`, `convert`, `styles`, `check-readers`.
- Verified, resumable downloads: temporary file names, size and checksum checks where the provider announces them, retries with back-off, connection limits per service, and JSON manifests with SHA-256 checksums, licence and attribution.
- Providers (each tested on real downloads): EUMETSAT Data Store, NOAA open data on AWS, DWD open data, NASA Earthdata (CMR), STAC catalogues (Microsoft Planetary Computer, AWS Earth Search, Copernicus Data Space), ECMWF Open Data, Copernicus Climate Data Store (ERA5), Copernicus Marine, ESGF (CMIP6 and CMIP5 tested).
- Product discovery: `eo-fetch products` and `eof.products()` with descriptions for all product aliases and live catalogue search.
- Readers for NetCDF, HDF5, Zarr, GRIB, GeoTIFF/JPEG 2000, gzip/bzip2/zip containers, MSG SEVIRI, MTG FCI, GOES ABI and DWD radar composites; regridding of projected data; map plots in a shared style registry (earthkit-plots); earthkit-data bridge.
- `eo-fetch login` for NASA Earthdata, EUMETSAT, CDS, Copernicus Marine and Copernicus Data Space credentials (stored in the user's folder, never in manifests).
- Dockerfile.

### Known limits

- No readers yet for BUFR, DWD station zips, radar `.tar` composites, NEXRAD; ICON icosahedral grids open without coordinates.
- ESGF projects other than CMIP6 and CMIP5 are untested; older projects need `--param indices=all`.
