"""Provider card: Deutscher Wetterdienst (DWD) open data server."""

from eo_fetch.providers import ProviderInfo, register

register(
    ProviderInfo(
        name="dwd",
        backend="http-index",
        title="DWD open data (opendata.dwd.de): radar, numerical models, climate data centre",
        auth="none",
        licence=(
            "DWD open data under the Geo Data Use Ordinance (GeoNutzV) and DWD's terms of use; "
            "the source must be named. Check the current terms for each dataset."
        ),
        attribution="Source: Deutscher Wetterdienst (DWD)",
        latency="radar and model data within minutes to hours; climate archives are versioned",
        notes=(
            "The whole tree of opendata.dwd.de is reachable: give any folder below it as "
            "--product (for example weather/radar/radolan/yw) and refine with --param prefix=, "
            "--param depth=N, --text glob and --start/--end. The time is read from the file name "
            "when it has a date, otherwise it is the server's modification time. Radar and "
            "model files are removed from the server after some days, the CDC archives stay. "
            "RADOLAN YW files on the server are HDF5 (a different format from the tar archives "
            "of the historical RADKLIM data)."
        ),
        backend_params={"base_url": "https://opendata.dwd.de"},
        products={
            "radolan": "weather/radar/radolan",
            "radolan-yw": "weather/radar/radolan/yw",
            "radar-composite": "weather/radar/composite",
            "radvor": "weather/radar/radvor",
            "radar-sites": "weather/radar/sites",
            "satellite": "weather/satellite",
            "icon": "weather/nwp/icon",
            "icon-eu": "weather/nwp/icon-eu",
            "icon-d2": "weather/nwp/icon-d2",
            "icon-d2-grib": "weather/nwp/icon-d2/grib",
            "icon-eps": "weather/nwp/icon-eps",
            "cdc-grids-germany": "climate_environment/CDC/grids_germany",
            "cdc-grids-europe": "climate_environment/CDC/grids_europe",
            "cdc-grids-5min-radolan": "climate_environment/CDC/grids_germany/5_minutes/radolan",
            "cdc-observations-germany": "climate_environment/CDC/observations_germany",
            "cdc-air-temperature-hourly-recent": (
                "climate_environment/CDC/observations_germany/climate/hourly/air_temperature/recent"
            ),
            "cdc-regional-averages": "climate_environment/CDC/regional_averages_DE",
        },
        verified="2026-11-03",
    )
)
