"""Provider card: NOAA open data on AWS (anonymous S3 buckets)."""

from eo_fetch.providers import ProviderInfo, register

GOES_PRODUCTS = {
    "cmip-conus": "ABI-L2-CMIPC",
    "cmip-fulldisk": "ABI-L2-CMIPF",
    "cmip-mesoscale": "ABI-L2-CMIPM",
    "mcmip-conus": "ABI-L2-MCMIPC",
    "radiance-conus": "ABI-L1b-RadC",
    "radiance-fulldisk": "ABI-L1b-RadF",
    "lightning": "GLM-L2-LCFA",
}

products = {
    f"goes{satellite}-{alias}": f"noaa-goes{satellite}/{prefix}"
    for satellite in (16, 18, 19)
    for alias, prefix in GOES_PRODUCTS.items()
}

# Buckets listed anonymously from a home connection on 2026-11-03 (spikes/06_noaa_buckets.py).
products.update(
    {
        "mrms": "noaa-mrms-pds",
        "gfs": "noaa-gfs-bdp-pds",
        "gefs": "noaa-gefs-pds",
        "hrrr": "noaa-hrrr-bdp-pds",
        "rap": "noaa-rap-pds",
        "nbm": "noaa-nbm-grib2-pds",
        "ghcn-daily": "noaa-ghcn-pds",
        "persiann-cdr": "noaa-cdr-precip-persiann-pds",
        "nodd-kerchunk": "noaa-nodd-kerchunk-pds",
        "viirs-noaa20": "noaa-nesdis-n20-pds",
        "jpss": "noaa-jpss",
        # NEXRAD Level II: the Unidata bucket lists anonymously (noaa-nexrad-level2 does not);
        # layout YYYY/MM/DD/SITE/, for example --param prefix=2026/09/15/KFWS/
        "nexrad-level2": "unidata-nexrad-level2",
        "nexrad-level2-chunks": "unidata-nexrad-level2-chunks",
    }
)

register(
    ProviderInfo(
        name="noaa",
        backend="s3",
        title="NOAA open data on AWS: GOES-R (16, 18, 19) and other public NOAA buckets",
        auth="none",
        licence=(
            "NOAA open data (NOAA Open Data Dissemination programme): freely available. "
            "Check the page of each dataset for any citation request."
        ),
        attribution="Data provided by NOAA (NEXRAD Level II archive hosted by Unidata)",
        latency="GOES-R files appear within minutes of the scan",
        notes=(
            "Any public bucket is reachable as --product bucket/prefix. GOES-R products take "
            "--start and --end and only list the hourly folders in between; other buckets take "
            "--param prefix=folder/ and --text glob. Channel filter for GOES: --text '*C13*'. "
            "Model buckets are organised by date and cycle, for example "
            "--product gfs --param prefix=gfs.20260915/12/atmos/. If a folder holds only "
            "subfolders, the search names them; --param depth=2 lists deeper. Some buckets "
            "refuse anonymous listing (noaa-nexrad-level2 answered Access Denied on 2026-11-03; "
            "the Unidata bucket works), so a bucket name from a web page may need checking."
        ),
        products=products,
        verified="2026-11-03",
    )
)
