"""Command line: providers, search, download, verify, doctor."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from eo_fetch import __version__
from eo_fetch.backends import get_backend
from eo_fetch.download import Result, download_items
from eo_fetch.manifest import build_manifest, verify_manifest, write_manifest
from eo_fetch.models import Item, Query
from eo_fetch.providers import all_providers, get_provider


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


def resolve(args: argparse.Namespace):
    """Return the provider info, the backend and the query for the parsed arguments."""
    info = get_provider(args.provider)
    user_params = parse_params(args.param)
    backend = get_backend(info.backend, {**info.backend_params, **user_params})
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
    size = f"{item.size / 1e6:.1f} MB" if item.size is not None else "? MB"
    return f"{when}  {size:>10}  {item.key}"


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
    total = sum(item.size or 0 for item in items)
    print(f"{len(items)} items, {total / 1e6:.1f} MB (sizes unknown for some items count as 0)")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    info, backend, query = resolve(args)
    items = backend.search(query)
    total = sum(item.size or 0 for item in items)
    print(f"{len(items)} items, {total / 1e6:.1f} MB")
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
    backend = get_backend(info.backend, {**info.backend_params, **parse_params(args.param)})
    print(f"{info.name}: {info.title}")
    print(f"  access: {info.auth}; latency: {info.latency or 'not stated'}")
    print(f"  licence: {info.licence or 'not stated'}")
    check = getattr(backend, "doctor", None)
    if check is None:
        print("  no access diagnostics implemented for this backend yet")
        return 0
    chosen = tuple(info.products.get(c, c) for c in args.collection)
    return 0 if (check(chosen) if chosen else check()) else 1


def cmd_collections(args: argparse.Namespace) -> int:
    info = get_provider(args.provider)
    backend = get_backend(info.backend, {**info.backend_params, **parse_params(args.param)})
    lister = getattr(backend, "collections", None)
    if lister is None:
        print(f"The {info.backend} backend has no collection listing.")
        return 1
    found = lister(args.text)
    for ident, title in found:
        print(f"{ident:36} {title}")
    print(f"{len(found)} collections")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eo-fetch", description=__doc__)
    parser.add_argument("--version", action="version", version=f"eo-fetch {__version__}")
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

    collections = sub.add_parser("collections", help="list the collections of a provider")
    collections.add_argument("--provider", required=True)
    collections.add_argument("--text", default="", help="only collections containing this text")
    collections.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    collections.set_defaults(run=cmd_collections)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except KeyError as error:
        print(error.args[0], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
