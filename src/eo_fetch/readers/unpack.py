"""Recognise files by their first bytes and unpack gzip, bzip2 and zip containers."""

from __future__ import annotations

import bz2
import gzip
import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

MAGIC = (
    (b"PK\x03\x04", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\x89HDF\r\n\x1a\n", "hdf5"),
    (b"CDF\x01", "netcdf"),
    (b"CDF\x02", "netcdf"),
    (b"GRIB", "grib"),
    (b"II*\x00", "geotiff"),
    (b"MM\x00*", "geotiff"),
    (b"II+\x00", "geotiff"),
)


def sniff(path: Path) -> str | None:
    """Name the kind of a file from its first bytes (zip, gzip, bzip2, hdf5, netcdf, grib, ...)."""
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        head = handle.read(8)
    for prefix, kind in MAGIC:
        if head.startswith(prefix):
            return kind
    return None


def unpacked_dir(path: Path) -> Path:
    """Where the contents of a container go: a short path under the temp folder.

    Zip members can have names of 150 characters and Windows stops at 260 characters per path,
    so the folder next to a deep download would be too long. Set EO_FETCH_CACHE to choose the
    place; unpacked files are reused when the same file is opened again.
    """
    root = Path(os.environ.get("EO_FETCH_CACHE") or tempfile.gettempdir()) / "eo-fetch-unpacked"
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:10]
    return root / key


def unpack_compressed(path: Path, kind: str) -> Path:
    """Decompress a .gz or .bz2 file next to it (once) and return the result."""
    folder = unpacked_dir(path)
    inner = path.name.rsplit(".", 1)[0] if path.suffix.lower() in {".gz", ".bz2"} else path.name
    target = folder / (inner if inner != path.name else path.name + ".out")
    if target.is_file() and target.stat().st_size > 0:
        return target
    folder.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if kind == "gzip" else bz2.open
    partial = target.with_name(target.name + ".part")
    with opener(path, "rb") as source, partial.open("wb") as out:
        shutil.copyfileobj(source, out, 1024 * 1024)
    partial.replace(target)
    return target


def zip_members(path: Path) -> list[str]:
    """Names of the files inside a zip."""
    with zipfile.ZipFile(path) as archive:
        return [name for name in archive.namelist() if not name.endswith("/")]


def unpack_zip(path: Path) -> list[Path]:
    """Extract a zip next to it (once) and return the extracted files."""
    folder = unpacked_dir(path)
    if not folder.is_dir() or not any(folder.iterdir()):
        folder.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(folder)
    return sorted(p for p in folder.rglob("*") if p.is_file())
