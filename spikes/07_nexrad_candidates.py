"""Spike 7: which NEXRAD Level II bucket lists anonymously, and with what folder layout?"""

from __future__ import annotations

import s3fs

CANDIDATES = [
    ("unidata-nexrad-level2", ""),
    ("unidata-nexrad-level2", "2026/09/15/KFWS/"),
    ("noaa-nexrad-level2", "2026/09/15/KFWS/"),
    ("unidata-nexrad-level2-chunks", ""),
    ("noaa-nexrad-level3", ""),
]


def main() -> None:
    fs = s3fs.S3FileSystem(anon=True)
    for bucket, prefix in CANDIDATES:
        path = f"{bucket}/{prefix}"
        try:
            entries = fs.ls(path, detail=False)
            names = [entry.rsplit("/", 1)[-1] for entry in entries[:4]]
            print(f"ok       {path:50s} {len(entries):5d} entries, first: {names}")
        except Exception as error:
            print(f"failed   {path:50s} {type(error).__name__}: {str(error)[:60]}")


if __name__ == "__main__":
    main()
