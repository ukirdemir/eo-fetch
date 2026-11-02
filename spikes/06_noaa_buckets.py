"""Spike 6: which NOAA open-data buckets on AWS can be listed anonymously from here?"""

from __future__ import annotations

import s3fs

BUCKETS = [
    "noaa-goes16",
    "noaa-goes18",
    "noaa-goes19",
    "noaa-nexrad-level2",
    "noaa-mrms-pds",
    "noaa-gfs-bdp-pds",
    "noaa-gefs-pds",
    "noaa-hrrr-bdp-pds",
    "noaa-rap-pds",
    "noaa-nbm-grib2-pds",
    "noaa-nws-rtma-pds",
    "noaa-oisst-feb-2025-pds",
    "noaa-ghcn-pds",
    "noaa-cdr-precip-persiann-pds",
    "noaa-nodd-kerchunk-pds",
    "noaa-viirs-snpp-pds",
    "noaa-nesdis-n20-pds",
    "noaa-jpss",
]


def main() -> None:
    fs = s3fs.S3FileSystem(anon=True)
    for bucket in BUCKETS:
        try:
            entries = fs.ls(bucket, detail=False)
            names = [entry.split("/", 1)[1] for entry in entries[:6]]
            more = " ..." if len(entries) > 6 else ""
            print(f"ok       {bucket:32s} {len(entries):4d} top-level entries: {names}{more}")
        except Exception as error:
            print(f"failed   {bucket:32s} {type(error).__name__}: {str(error)[:70]}")


if __name__ == "__main__":
    main()
