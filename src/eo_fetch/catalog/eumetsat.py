"""Provider card: EUMETSAT Data Store."""

from eo_fetch.registry import ProviderInfo, register

register(
    ProviderInfo(
        name="eumetsat",
        backend="eumetsat",
        title="EUMETSAT Data Store: Meteosat, MTG, Metop, Sentinel-3/5P/6 and CM SAF data",
        auth="licence",
        licence=(
            "EUMETSAT Data Policy; access depends on the licences activated for your account "
            "(for example Meteosat data older than one hour, or near-real-time data for "
            "research and education). Check the current terms before redistributing."
        ),
        attribution="Contains modified EUMETSAT data",
        latency="depends on the collection: near real time to climate data records",
        notes=(
            "Needs an Earth Observation Portal account, API keys (EUMETSAT_KEY and "
            "EUMETSAT_SECRET, or ~/.eumdac/credentials) and the licence of the collection. "
            "At most 2 parallel downloads. List collections with "
            "`eo-fetch collections --provider eumetsat`."
        ),
        products={
            "seviri": "EO:EUM:DAT:MSG:HRSEVIRI",
            "seviri-iodc": "EO:EUM:DAT:MSG:HRSEVIRI-IODC",
            "seviri-rss": "EO:EUM:DAT:MSG:MSG15-RSS",
            "seviri-cloud-mask": "EO:EUM:DAT:MSG:CLM",
            "seviri-cloud-top-height": "EO:EUM:DAT:MSG:CTH",
            "fci-normal": "EO:EUM:DAT:0662",
            "fci-high": "EO:EUM:DAT:0665",
            "fci-cloud-mask": "EO:EUM:DAT:0678",
            "mtg-precip-rate": "EO:EUM:DAT:1086",
            "mtg-lightning-flashes": "EO:EUM:DAT:0691",
            "metop-iasi-l1c": "EO:EUM:DAT:METOP:IASIL1C-ALL",
            "metop-ascat-soil-moisture-25km": "EO:EUM:DAT:METOP:SOMO25",
            "cmsaf-sarah3": "EO:EUM:DAT:0863",
            "cmsaf-girafe-rainfall": "EO:EUM:DAT:0921",
        },
        verified="2026-11-02",
    )
)
