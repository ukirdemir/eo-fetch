"""Provider card: NASA Earthdata (the whole Common Metadata Repository)."""

from eo_fetch.registry import ProviderInfo, register

register(
    ProviderInfo(
        name="nasa",
        backend="nasa",
        title="NASA Earthdata: every collection of the Common Metadata Repository (CMR)",
        auth="account",
        licence=(
            "NASA data are open, but downloads need a free Earthdata Login account, and some "
            "providers (for example GES DISC) need you to approve their application once at "
            "urs.earthdata.nasa.gov > Applications > Authorized Apps."
        ),
        attribution="Data provided by NASA Earthdata; cite the collection's DOI as listed in CMR",
        latency="IMERG Late about 14 hours; IMERG Final several months; other products vary",
        notes=(
            "--product is any collection short name (optionally SHORT_NAME@VERSION; the newest "
            "version is used by default) or a concept id. Find collections with "
            "`eo-fetch collections --provider nasa --text keyword`. Search needs --start/--end "
            "or --limit. Credentials: EARTHDATA_USERNAME and EARTHDATA_PASSWORD, ~/.netrc, or "
            "the terminal prompt; they are never stored by eo-fetch."
        ),
        products={
            "imerg-late-daily": "GPM_3IMERGDL",
            "imerg-late-halfhourly": "GPM_3IMERGHHL",
            "imerg-final-daily": "GPM_3IMERGDF",
            "imerg-final-halfhourly": "GPM_3IMERGHH",
            "imerg-final-monthly": "GPM_3IMERGM",
            "omi-no2-daily": "OMNO2d",
            "smap-soil-moisture-daily": "SPL3SMP",
            "merra2-surface-hourly": "M2T1NXSLV",
        },
        verified="2026-11-03",
    )
)
