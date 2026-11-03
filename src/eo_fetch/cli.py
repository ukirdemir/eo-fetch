"""Command line: providers, search, download, verify, doctor."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from eo_fetch import __version__
from eo_fetch.backends import get_backend, param_names
from eo_fetch.download import Result, download_items
from eo_fetch.manifest import build_manifest, verify_manifest, write_manifest
from eo_fetch.models import Item, Query
from eo_fetch.providers import ProviderInfo, all_providers, get_provider


def parse_time(text: str) -> datetime:
    """Parse an ISO date or date-time; naive values are taken as UTC."""
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def parse_params(pairs: Sequence[str]) -> dict[str, str]:
    """Turn ``key=value`` strings into a dict."""
    params = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            raise SystemExit(f"Invalid --param {pair!r}: use key=value")
        params[key] = value
    return params


def add_query_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", required=True)
    parser.add_argument("--product", default="", help="product alias or the backend's own id")
    parser.add_argument("--start", type=parse_time, help="ISO date or date-time (UTC)")
    parser.add_argument("--end", type=parse_time, help="ISO date or date-time (UTC, exclusive)")
    parser.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    parser.add_argument("--text", default="", help="keyword, glob or id, depending on provider")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")


def build_backend(info: ProviderInfo, user_params: dict[str, str]):
    """Create the provider's backend, rejecting --param names it does not know."""
    constructor, search = param_names(info.backend)
    unknown = set(user_params) - constructor - search
    if unknown:
        accepted = ", ".join(sorted(constructor | search)) or "none"
        raise SystemExit(
            f"Unknown --param {', '.join(sorted(unknown))} for provider {info.name} "
            f"(accepted: {accepted})"
        )
    return get_backend(info.backend, {**info.backend_params, **user_params})


def resolve(args: argparse.Namespace):
    """Return the provider info, the backend and the query for the parsed arguments."""
    info = get_provider(args.provider)
    user_params = parse_params(args.param)
    backend = build_backend(info, user_params)
    product = info.products.get(args.product, args.product)
    query = Query(
        provider=info.name,
        product=product,
        start=args.start,
        end=args.end,
        bbox=tuple(args.bbox) if args.bbox else None,
        text=args.text,
        limit=args.limit,
        params=user_params,
    )
    return info, backend, query


def describe(item: Item) -> str:
    when = item.time.strftime("%Y-%m-%d %H:%M") if item.time else "-"
    expected = item.expected_size
    size = f"{expected / 1e6:.1f} MB" if expected is not None else "? MB"
    return f"{when}  {size:>10}  {item.key}"


def total_megabytes(items: Sequence[Item]) -> float:
    """Sum of the known or approximate sizes in megabytes (unknown sizes count as 0)."""
    return sum(item.expected_size or 0 for item in items) / 1e6


def cmd_providers(args: argparse.Namespace) -> int:
    print(f"{'name':16} {'backend':12} {'auth':8} {'verified':10} title")
    for info in all_providers():
        verified = info.verified or "-"
        print(f"{info.name:16} {info.backend:12} {info.auth:8} {verified:10} {info.title}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    _, backend, query = resolve(args)
    items = backend.search(query)
    for item in items:
        print(describe(item))
    unknown = sum(item.expected_size is None for item in items)
    note = f" ({unknown} of unknown size)" if unknown else ""
    print(f"{len(items)} items, {total_megabytes(items):.1f} MB{note}")
    folders = getattr(backend, "folders_seen", [])
    if not items and folders:
        shown = ", ".join(name.rsplit("/", 1)[-1] for name in folders[:12])
        more = " ..." if len(folders) > 12 else ""
        print(f"No files here, but {len(folders)} subfolders: {shown}{more}")
        print("Give one with --param prefix=..., or look deeper with --param depth=2")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    info, backend, query = resolve(args)
    items = backend.search(query)
    print(f"{len(items)} items, {total_megabytes(items):.1f} MB")
    if args.dry_run or not items:
        return 0

    def report(result: Result) -> None:
        note = f"  {result.error}" if result.error else ""
        print(f"  {result.status:10} {result.item.key}{note}")

    results = download_items(
        backend, items, args.dest, workers=args.workers, retries=args.retries, on_result=report
    )
    manifest = args.manifest or args.dest / "manifest.json"
    write_manifest(manifest, build_manifest(query, info, results))
    failed = sum(r.status == "failed" for r in results)
    print(f"Manifest: {manifest}; {len(results) - failed} ok, {failed} failed")
    return 1 if failed else 0


def cmd_verify(args: argparse.Namespace) -> int:
    problems = verify_manifest(args.manifest, args.root)
    for problem in problems:
        print(problem)
    print("OK" if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    info = get_provider(args.provider)
    backend = build_backend(info, parse_params(args.param))
    print(f"{info.name}: {info.title}")
    print(f"  access: {info.auth}; latency: {info.latency or 'not stated'}")
    print(f"  licence: {info.licence or 'not stated'}")
    check = getattr(backend, "doctor", None)
    if check is None:
        print("  no access diagnostics implemented for this backend yet")
        return 0
    chosen = tuple(info.products.get(c, c) for c in args.collection)
    # an empty choice makes the backend use its own default probe collection
    return 0 if (check(chosen) if chosen else check()) else 1


def cmd_login(args: argparse.Namespace) -> int:
    info = get_provider(args.provider)
    backend = build_backend(info, {})
    login = getattr(backend, "login", None)
    if login is None:
        print(
            f"{info.name} has no login step in eo-fetch. See `eo-fetch doctor --provider "
            f"{info.name}` for how its credentials are found."
        )
        return 1
    login()
    return 0


def cmd_collections(args: argparse.Namespace) -> int:
    info = get_provider(args.provider)
    backend = build_backend(info, parse_params(args.param))
    lister = getattr(backend, "collections", None)
    if lister is None:
        print(f"The {info.backend} backend has no collection listing.")
        return 1
    found = lister(args.text)
    for ident, title in found:
        print(f"{ident:36} {title}")
    print(f"{len(found)} collections")
    return 0


def parse_options(pairs: Sequence[str]) -> dict[str, object]:
    """Reader options from ``key=value``; numbers are converted, ``a,b`` stays a string."""
    options: dict[str, object] = {}
    for key, value in parse_params(pairs).items():
        if key == "area_extent":
            options[key] = tuple(float(part) for part in value.split(","))
            continue
        try:
            options[key] = float(value)
        except ValueError:
            options[key] = value
    return options


def cmd_open(args: argparse.Namespace) -> int:
    from eo_fetch.readers import open_data, resolve, summarize

    format_name = args.format or "+".join(sorted({name for name, _ in resolve(args.path)}))
    dataset = open_data(args.path, format=args.format, **parse_options(args.option))
    print(f"{args.path.name}: format {format_name}")
    print(summarize(dataset))
    return 0


def cmd_plot(args: argparse.Namespace) -> int:
    from eo_fetch import plotting

    output = args.output or Path("plots") / (args.path.stem[:60] + ".png")
    used = plotting.plot(
        args.path,
        output,
        variable=args.variable,
        style=args.style,
        domain=args.domain,
        resolution=args.resolution,
        bbox=tuple(args.bbox) if args.bbox else None,
        title=args.title,
        format=args.format,
        **parse_options(args.option),
    )
    print(f"Saved {output} (style: {used})")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    from eo_fetch import bridge

    output = bridge.convert(
        args.path,
        args.output,
        resolution=args.resolution,
        bbox=tuple(args.bbox) if args.bbox else None,
        format=args.format,
        **parse_options(args.option),
    )
    print(f"Wrote {output}")
    return 0


def cmd_styles(args: argparse.Namespace) -> int:
    from eo_fetch.styles import STYLES

    for style in STYLES.values():
        print(f"{style.name:20} {style.label:6} {style.description}")
    return 0


def cmd_check_readers(args: argparse.Namespace) -> int:
    from eo_fetch import checkreaders

    def make(info: ProviderInfo):
        return build_backend(info, {})

    def show(row: checkreaders.Row) -> None:
        print(f"{row.status:10} {row.provider}/{row.product:32} {row.format:8} {row.detail}")

    rows = checkreaders.run(
        make, args.dest, args.only, days=args.days, max_mb=args.max_mb, on_row=show
    )
    counts = {s: sum(r.status == s for r in rows) for s in ("ok", "no reader", "fail", "skip")}
    print(", ".join(f"{count} {status}" for status, count in counts.items()))
    return 1 if counts["fail"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eo-fetch", description=__doc__)
    parser.add_argument("--version", action="version", version=f"eo-fetch {__version__}")
    parser.add_argument("--debug", action="store_true", help="show full tracebacks on errors")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("providers", help="list registered providers").set_defaults(run=cmd_providers)

    search = sub.add_parser("search", help="list items matching a query")
    add_query_options(search)
    search.set_defaults(run=cmd_search)

    download = sub.add_parser("download", help="download items and write a manifest")
    add_query_options(download)
    download.add_argument("--dest", type=Path, required=True)
    download.add_argument("--manifest", type=Path)
    download.add_argument("--workers", type=int)
    download.add_argument("--retries", type=int, default=3)
    download.add_argument("--dry-run", action="store_true", help="only list and sum the sizes")
    download.set_defaults(run=cmd_download)

    verify = sub.add_parser("verify", help="check downloaded files against a manifest")
    verify.add_argument("manifest", type=Path)
    verify.add_argument("--root", type=Path, required=True, help="folder holding the files")
    verify.set_defaults(run=cmd_verify)

    doctor = sub.add_parser("doctor", help="check access (credentials, licences) for a provider")
    doctor.add_argument("--provider", required=True)
    doctor.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    doctor.add_argument(
        "--collection", action="append", default=[], help="collection or alias to test"
    )
    doctor.set_defaults(run=cmd_doctor)

    login = sub.add_parser(
        "login", help="log in once and save the login (providers that support it)"
    )
    login.add_argument("--provider", required=True)
    login.set_defaults(run=cmd_login)

    collections = sub.add_parser("collections", help="list the collections of a provider")
    collections.add_argument("--provider", required=True)
    collections.add_argument("--text", default="", help="only collections containing this text")
    collections.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    collections.set_defaults(run=cmd_collections)

    open_cmd = sub.add_parser("open", help="open a downloaded file and describe its contents")
    open_cmd.add_argument("path", type=Path)
    open_cmd.add_argument("--format", help="override the detected format")
    open_cmd.add_argument(
        "--option", action="append", default=[], metavar="KEY=VALUE", help="reader option"
    )
    open_cmd.set_defaults(run=cmd_open)

    plot_cmd = sub.add_parser("plot", help="draw a downloaded file on a map")
    plot_cmd.add_argument("path", type=Path)
    plot_cmd.add_argument("--output", type=Path, help="PNG file (default plots/<name>.png)")
    plot_cmd.add_argument("--variable")
    plot_cmd.add_argument("--style", help="style name, see 'eo-fetch styles' (default: automatic)")
    plot_cmd.add_argument("--domain", help="earthkit-plots domain name, e.g. Europe")
    plot_cmd.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    plot_cmd.add_argument("--resolution", type=float, help="degrees, for projected data")
    plot_cmd.add_argument("--title")
    plot_cmd.add_argument("--format", help="override the detected file format")
    plot_cmd.add_argument(
        "--option", action="append", default=[], metavar="KEY=VALUE", help="reader option"
    )
    plot_cmd.set_defaults(run=cmd_plot)

    convert_cmd = sub.add_parser("convert", help="write a readable file as NetCDF or Zarr")
    convert_cmd.add_argument("path", type=Path)
    convert_cmd.add_argument("output", type=Path, help="file ending in .nc or .zarr")
    convert_cmd.add_argument("--resolution", type=float, help="regrid projected data (degrees)")
    convert_cmd.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    convert_cmd.add_argument("--format", help="override the detected file format")
    convert_cmd.add_argument(
        "--option", action="append", default=[], metavar="KEY=VALUE", help="reader option"
    )
    convert_cmd.set_defaults(run=cmd_convert)

    sub.add_parser("styles", help="list the plot styles").set_defaults(run=cmd_styles)

    check = sub.add_parser(
        "check-readers", help="download the smallest recent file of each product and open it"
    )
    check.add_argument("--dest", type=Path, default=Path("check_readers"))
    check.add_argument("--only", action="append", default=[], metavar="PROVIDER[/ALIAS]")
    check.add_argument("--days", type=int, default=3, help="look at files of the last N days")
    check.add_argument("--max-mb", type=float, default=300.0)
    check.set_defaults(run=cmd_check_readers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except KeyError as error:
        print(error.args[0], file=sys.stderr)
        return 2
    except (ValueError, RuntimeError, OSError) as error:
        if args.debug:
            raise
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
