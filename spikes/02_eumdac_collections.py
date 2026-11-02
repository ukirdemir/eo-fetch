"""Spike 2: list every collection the EUMETSAT Data Store offers (needs ~/.eumdac/credentials)."""

from __future__ import annotations

from pathlib import Path

import eumdac


def main() -> None:
    text = (Path.home() / ".eumdac" / "credentials").read_text().strip()
    key, secret = text.split(",")[:2]
    datastore = eumdac.DataStore(eumdac.AccessToken((key.strip(), secret.strip())))
    collections = list(datastore.collections)
    print(f"{len(collections)} collections")
    for collection in sorted(collections, key=lambda c: str(c)):
        print(f"  {collection!s:40s} {collection.title}")


if __name__ == "__main__":
    main()
