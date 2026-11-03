"""One registry of plot styles, so that every dataset is drawn in the same visual language.

A style is plain data (colours, levels, label); ``to_earthkit`` turns it into an earthkit-plots
style. ``pick_style`` chooses by the variable's name, units and descriptive attributes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PlotStyle:
    name: str
    colors: str | tuple[str, ...]  # a matplotlib colormap name or a list of colours
    levels: tuple[float, ...] = ()
    label: str = ""  # units label for the legend and title
    extend: str = "neither"  # neither, min, max, both
    categories: tuple[str, ...] = ()  # labels for categorical data
    description: str = ""


def steps(start: float, stop: float, step: float) -> tuple[float, ...]:
    count = round((stop - start) / step)
    return tuple(round(start + i * step, 6) for i in range(count + 1))


STYLES: dict[str, PlotStyle] = {
    style.name: style
    for style in (
        PlotStyle(
            "precip-rate",
            "YlGnBu",
            (0.1, 0.5, 1, 2, 5, 10, 20, 50, 100),
            "mm/h",
            "max",
            description="Rain rate; light blue for drizzle to dark blue for extreme rain",
        ),
        PlotStyle(
            "precip-daily",
            "YlGnBu",
            (0.5, 1, 2, 5, 10, 20, 50, 100, 200),
            "mm/day",
            "max",
            description="Daily mean precipitation rate (IMERG daily and similar)",
        ),
        PlotStyle(
            "precip-accumulation",
            "YlGnBu",
            (0.1, 1, 2, 5, 10, 20, 50, 100, 200),
            "mm",
            "max",
            description="Accumulated precipitation",
        ),
        PlotStyle(
            "ir-brightness",
            "gray_r",
            steps(190, 320, 5),
            "K",
            "both",
            description="Infrared brightness temperature: cold, high clouds are white",
        ),
        PlotStyle(
            "wv-brightness",
            "cividis_r",
            steps(200, 260, 2),
            "K",
            "both",
            description="Water vapour brightness temperature",
        ),
        PlotStyle(
            "temperature-k",
            "RdYlBu_r",
            steps(230, 320, 5),
            "K",
            "both",
            description="Air or surface temperature in kelvin",
        ),
        PlotStyle(
            "temperature-c",
            "RdYlBu_r",
            steps(-30, 45, 5),
            "degC",
            "both",
            description="Air or surface temperature in degrees Celsius",
        ),
        PlotStyle(
            "reflectivity",
            "turbo",
            steps(5, 70, 5),
            "dBZ",
            "max",
            description="Radar reflectivity",
        ),
        PlotStyle(
            "reflectance",
            "gray",
            steps(0, 100, 5),
            "%",
            "max",
            description="Visible and near-infrared reflectance in percent",
        ),
        PlotStyle(
            "reflectance-fraction",
            "gray",
            steps(0, 1, 0.05),
            "1",
            "max",
            description="Visible and near-infrared reflectance as a fraction (0 to 1)",
        ),
        PlotStyle(
            "cloud-top-height",
            "viridis",
            steps(0, 14000, 1000),
            "m",
            "max",
            description="Cloud top height",
        ),
        PlotStyle(
            "cloud-mask",
            ("#2a6fb0", "#6a9a3e", "#ffffff", "#555555"),
            (0, 1, 2, 3, 4),
            "",
            "neither",
            ("clear sea", "clear land", "cloudy", "no data"),
            "SEVIRI cloud classification",
        ),
        PlotStyle(
            "radiation",
            "magma",
            steps(0, 1000, 100),
            "W m-2",
            "max",
            description="Radiation flux",
        ),
    )
}

# (words to find in the variable name and descriptive attributes, units, style name);
# the first matching rule wins, so specific rules come first.
RULES: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("cloud_mask", "cloud_classification", "clm"), (), "cloud-mask"),
    (("cloud_top_height", "height_at_cloud_top"), (), "cloud-top-height"),
    (("ir_", "c13", "c14", "c15", "c11", "c07", "brightness"), ("k",), "ir-brightness"),
    (("wv_", "c08", "c09", "c10"), ("k",), "wv-brightness"),
    (("rain", "precip", "rate", "rainfall"), ("mm/h", "mm h-1", "mm hr-1"), "precip-rate"),
    (("rain", "precip"), ("mm/day", "mm d-1", "mm/d", "mm day-1"), "precip-daily"),
    (("rain", "precip", "acrr", "accum"), ("mm", "kg m-2"), "precip-accumulation"),
    (("dbz", "reflectivity"), ("dbz",), "reflectivity"),
    (("refl", "cmi", "albedo"), ("%", "percent"), "reflectance"),
    (("refl", "cmi", "albedo"), ("1", "", "dimensionless"), "reflectance-fraction"),
    (("sis", "radiation", "irradiance", "dni", "ssr"), ("w m-2", "w/m2", "w m**-2"), "radiation"),
    (("temp", "t2m", "2t", "sst", "skt"), ("k", "kelvin"), "temperature-k"),
    (
        ("temp", "t2m", "2t", "sst", "skt"),
        ("degc", "celsius", "c", "degree_celsius"),
        "temperature-c",
    ),
)


def pick_style(name: str, attrs: Mapping[str, object] | None = None) -> PlotStyle | None:
    """Choose a style for a variable, or None when nothing fits (the plot library decides)."""
    attrs = attrs or {}
    text = " ".join(
        str(value).lower()
        for value in (
            name,
            attrs.get("long_name", ""),
            attrs.get("standard_name", ""),
            attrs.get("quantity", ""),
        )
    )
    units = str(attrs.get("units", "")).strip().lower()
    for words, unit_options, style_name in RULES:
        if any(word in text for word in words) and (not unit_options or units in unit_options):
            return STYLES[style_name]
    return None


def get_style(name: str) -> PlotStyle:
    try:
        return STYLES[name]
    except KeyError:
        raise KeyError(f"Unknown style {name!r}. Available: {', '.join(sorted(STYLES))}") from None


def to_earthkit(style: PlotStyle):
    """Build the earthkit-plots style for a registry entry."""
    from earthkit.plots.styles import Style

    colors = list(style.colors) if isinstance(style.colors, tuple) else style.colors
    kwargs = {"colors": colors, "levels": list(style.levels), "extend": style.extend}
    if style.label:
        kwargs["units_label"] = style.label
    if style.categories:
        kwargs["categories"] = list(style.categories)
    return Style(**kwargs)
