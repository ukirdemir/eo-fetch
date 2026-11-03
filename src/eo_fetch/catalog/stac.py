"""Provider cards: STAC catalogues (Planetary Computer, AWS Earth Search, Copernicus Data Space)."""

from eo_fetch.providers import ProviderInfo, register

NOTES = (
    "--product is a STAC collection id (list them with `eo-fetch collections --provider NAME`); "
    "--param assets=KEY[,KEY] chooses the files of each scene (for example B04,B08 or visual); "
    "--limit counts files; --bbox and --start/--end filter scenes. "
)

register(
    ProviderInfo(
        name="planetary-computer",
        backend="stac",
        title="Microsoft Planetary Computer: Sentinel, Landsat, land cover, climate (STAC)",
        auth="none",
        licence=(
            "Each collection has its own licence, shown in its STAC record; most are open. "
            "Links are signed automatically with the free, anonymous planetary-computer package."
        ),
        attribution="Data via Microsoft Planetary Computer; credit the original data provider",
        latency="varies by collection",
        notes=NOTES + "Needs the planetary-computer package (extra: stac).",
        backend_params={
            "catalog_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
            "sign": "planetary-computer",
        },
        products={
            "sentinel-2": "sentinel-2-l2a",
            "sentinel-1-rtc": "sentinel-1-rtc",
            "landsat": "landsat-c2-l2",
            "land-cover-worldcover": "esa-worldcover",
            "land-use-lulc": "io-lulc-annual-v02",
            "era5": "era5-pds",
            "terraclimate": "terraclimate",
            "dem-nasadem": "nasadem",
        },
        verified="2026-11-04",
    )
)

register(
    ProviderInfo(
        name="earth-search",
        backend="stac",
        title="AWS Earth Search (Element 84): Sentinel-2, Sentinel-1, Copernicus DEM (STAC)",
        auth="none",
        licence=(
            "Sentinel data are free and open under the Copernicus licence; Landsat is public "
            "domain. Landsat on AWS is requester-pays and cannot be downloaded anonymously."
        ),
        attribution="Contains modified Copernicus Sentinel data; Landsat courtesy of USGS",
        latency="Sentinel-2 within hours",
        notes=NOTES + "Landsat assets are requester-pays on AWS and are not covered.",
        backend_params={"catalog_url": "https://earth-search.aws.element84.com/v1"},
        products={
            "sentinel-2": "sentinel-2-l2a",
            "sentinel-1": "sentinel-1-grd",
            "dem-30m": "cop-dem-glo-30",
            "dem-90m": "cop-dem-glo-90",
        },
        verified="2026-11-04",
    )
)

register(
    ProviderInfo(
        name="cdse",
        backend="stac",
        title="Copernicus Data Space Ecosystem: Sentinel missions (STAC)",
        auth="account",
        licence=(
            "Copernicus Sentinel data are free and open. Searching needs no account; downloading "
            "needs a free CDSE account and S3 keys (CDSE_S3_KEY, CDSE_S3_SECRET) from "
            "eodata-s3keysmanager.dataspace.copernicus.eu."
        ),
        attribution="Contains modified Copernicus Sentinel data",
        latency="Sentinel-2 and Sentinel-1 within hours",
        notes=NOTES + "Downloads go through the S3 endpoint eodata.dataspace.copernicus.eu.",
        backend_params={
            "catalog_url": "https://stac.dataspace.copernicus.eu/v1",
            "s3_endpoint": "https://eodata.dataspace.copernicus.eu",
        },
        products={"sentinel-2": "sentinel-2-l2a", "sentinel-1": "sentinel-1-grd"},
        verified="",
    )
)
