"""A manifest records exactly what was fetched, from where and under which terms."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eo_fetch import __version__
from eo_fetch.download import Result, file_digest
from eo_fetch.models import Query
from eo_fetch.providers import ProviderInfo


def build_manifest(query: Query, provider: ProviderInfo, results: list[Result]) -> dict:
    """Return a JSON-serialisable manifest for a download run."""
    return {
        "eo_fetch_version": __version__,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "query": {
            "provider": query.provider,
            "product": query.product,
            "start": query.start.isoformat() if query.start else None,
            "end": query.end.isoformat() if query.end else None,
            "bbox": list(query.bbox) if query.bbox else None,
            "text": query.text,
            "limit": query.limit,
            "params": dict(query.params),
        },
        "provider": {
            "name": provider.name,
            "title": provider.title,
            "licence": provider.licence,
            "attribution": provider.attribution,
        },
        "files": [
            {
                "key": r.item.key,
                "product": r.item.product,
                "time": r.item.time.isoformat() if r.item.time else None,
                "url": r.item.url,
                "path": r.path.name if r.path else None,
                "size": r.size,
                "sha256": r.sha256,
                "status": r.status,
                "error": r.error,
            }
            for r in results
        ],
    }


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def verify_manifest(path: Path, root: Path) -> list[str]:
    """Check every downloaded file against the manifest; return a list of problems."""
    manifest = json.loads(path.read_text())
    problems = []
    for entry in manifest["files"]:
        if not entry["path"]:
            problems.append(f"{entry['key']}: not downloaded ({entry['error'] or entry['status']})")
            continue
        file = root / entry["path"]
        if not file.is_file():
            problems.append(f"{entry['path']}: missing")
        elif file.stat().st_size != entry["size"]:
            problems.append(f"{entry['path']}: size differs")
        elif file_digest(file) != entry["sha256"]:
            problems.append(f"{entry['path']}: checksum differs")
    return problems
