"""Provider cards: ECMWF Open Data and the Copernicus Climate Data Store (ERA5)."""

from eo_fetch.registry import ProviderInfo, register

register(
    ProviderInfo(
        name="ecmwf-open-data",
        backend="ecmwf-opendata",
        title="ECMWF Open Data: IFS and ensemble forecasts, by parameter and lead time",
        auth="none",
        licence=(
            "ECMWF open data are released under the Creative Commons CC BY 4.0 licence; check "
            "ECMWF's current terms."
        ),
        attribution="Copyright ECMWF; data under CC BY 4.0",
        latency="forecasts appear a few hours after the cycle; only recent cycles are kept",
        notes=(
            "Plans one download per forecast cycle and lead time. --product is the stream: "
            "oper (high-resolution forecast) or enfo (ensemble). --param param=2t,msl,tp "
            "chooses parameters (default 2t), --param steps=0,6,12 or 0-48-6 the lead times in "
            "hours, --param cycles=00,12 the forecast hours. Without --start/--end the latest "
            "cycle is used. --param source=aws switches to the AWS mirror if the ECMWF portal "
            "is busy. Needs the ecmwf-opendata package (extra: ecmwf)."
        ),
        backend_params={"source": "ecmwf"},
        products={"ifs-hres": "oper", "ifs-ensemble": "enfo"},
        verified="2026-11-04",
    )
)

register(
    ProviderInfo(
        name="copernicus-marine",
        backend="marine",
        title="Copernicus Marine Service (CMEMS): ocean physics, biogeochemistry, sea ice, waves",
        auth="account",
        licence=(
            "Copernicus Marine products are free and open; a free account is needed to "
            "download. Cite each product's DOI."
        ),
        attribution=(
            "Generated using E.U. Copernicus Marine Service Information; cite the product DOI"
        ),
        latency="analysis and forecast products daily; reprocessed products months behind",
        notes=(
            "Plans one subset per month. --product is a dataset id (find them with "
            "`eo-fetch collections --provider copernicus-marine --text temperature`); "
            "--start and --end are required (end exclusive); --param variables=thetao,so "
            "(default all), min_depth and max_depth in metres, version. --bbox limits the "
            "area. Log in once with `eo-fetch login --provider copernicus-marine`. Subsets of "
            "large datasets can be big: use a small area, short time span and few variables."
        ),
        products={"sst-l4-nrt": "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"},
        verified="2026-11-04",
    )
)

register(
    ProviderInfo(
        name="esgf",
        backend="esgf",
        title="ESGF: CMIP climate-model output (CMIP5, CMIP6 tested), CORDEX, obs4MIPs",
        auth="none",
        licence=(
            "Each dataset carries its own licence (CMIP6 data are mostly CC BY 4.0); check the "
            "licence attribute inside the files."
        ),
        attribution="Cite the CMIP6/CMIP7 dataset DOIs and acknowledge the modelling groups",
        latency="published months to years after the model runs; nodes can be offline",
        notes=(
            "--product is the project: cmip3, cmip5, cmip6, cmip7, cordex-cmip6, input4mips or "
            "obs4mips (default: intake-esgf's default, currently CMIP7). CMIP6 and CMIP5 have "
            "been tested (CMIP5 needs --param indices=all); the other projects work only as far "
            "as the ESGF indices still serve them. "
            "Every --param is an ESGF facet, and facet names differ by project, e.g. CMIP6: "
            "--param variable_id=tas --param experiment_id=historical --param source_id=CanESM5 "
            "--param member_id=r1i1p1f1 --param table_id=Amon; CMIP5: variable, experiment, "
            "model, ensemble, time_frequency, cmor_table. A comma separates alternatives. "
            "--param indices=all also searches the legacy indices, which still hold older "
            "projects such as CMIP5 (slower); indices=-discovery.east.esgf.io,"
            "-discovery.west.esgf.io switches the STAC indices off (no CMIP6 warning). "
            "--start/--end keep files "
            "overlapping the period; --text is a free-text search; --bbox is not supported. "
            "Search is done by intake-esgf over several indices (the old Solr indices are being "
            "retired); the search asks every matching dataset for its files, so narrow the facets. "
            "Needs the intake-esgf package (extra: esgf)."
        ),
        products={
            "cmip3": "CMIP3",
            "cmip5": "CMIP5",
            "cmip6": "CMIP6",
            "cmip7": "CMIP7",
            "cordex-cmip6": "CORDEX-CMIP6",
            "input4mips": "input4MIPs",
            "obs4mips": "obs4MIPs",
        },
        verified="2026-11-05",
    )
)

register(
    ProviderInfo(
        name="cds",
        backend="cds",
        title="Copernicus Climate Data Store: ERA5 and ERA5-Land reanalysis (hourly)",
        auth="account",
        licence=(
            "Copernicus products are free; you must create a CDS account and accept each "
            "dataset's licence once on its page at cds.climate.copernicus.eu."
        ),
        attribution=(
            "Generated using Copernicus Climate Change Service information; cite the dataset DOI"
        ),
        latency="ERA5 is available about 5 days behind real time; requests queue before running",
        notes=(
            "Plans one request per month. --product is a dataset name (alias or "
            "reanalysis-era5-single-levels); --param variable=2m_temperature,total_precipitation "
            "is required; --start/--end are required (end exclusive). Other parameters: hours "
            "(default 00:00,06:00,12:00,18:00), format (grib or netcdf), level (hPa, for "
            "pressure-level data), extra (JSON merged into the request). --bbox restricts the "
            "area. Credentials in ~/.cdsapirc, never in eo-fetch. Requests can wait in the CDS "
            "queue for a long time; keep requests small."
        ),
        products={
            "era5-single-levels": "reanalysis-era5-single-levels",
            "era5-pressure-levels": "reanalysis-era5-pressure-levels",
            "era5-land": "reanalysis-era5-land",
        },
        verified="2026-11-04",
    )
)
