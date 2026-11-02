"""Spike 4: search NASA Earthdata (CMR) for IMERG granules with earthaccess.

earthaccess.login() uses EARTHDATA_USERNAME/EARTHDATA_PASSWORD (or a token), then ~/.netrc, and
otherwise asks for your credentials in the terminal. Nothing is stored by this script.

The Final run (GPM_3IMERGDF) comes months after the observation; the Late run (GPM_3IMERGDL)
about 14 hours after. This spike finds out where the Final run currently ends.
"""

from __future__ import annotations

import earthaccess

SEARCHES = [
    ("GPM_3IMERGDL", ("2026-09-01", "2026-09-03")),
    ("GPM_3IMERGDF", ("2025-06-01", "2025-06-03")),
    ("GPM_3IMERGDF", ("2026-01-01", "2026-01-03")),
    ("GPM_3IMERGDF", ("2026-03-01", "2026-03-03")),
    ("GPM_3IMERGDF", ("2026-05-01", "2026-05-03")),
]


def value(obj, name):
    """Return an attribute or the result of a method, depending on the earthaccess version."""
    attribute = getattr(obj, name)
    return attribute() if callable(attribute) else attribute


def main() -> None:
    auth = earthaccess.login()
    print(f"Authenticated: {auth.authenticated}")
    for short_name, period in SEARCHES:
        results = earthaccess.search_data(short_name=short_name, temporal=period, count=5)
        print(f"{short_name} {period}: {len(results)} granules")
        for granule in results[:1]:
            links = value(granule, "data_links")
            print(f"  {links[0] if links else '-'}  ({value(granule, 'size')} MB)")
    collections = earthaccess.search_datasets(keyword="IMERG", count=10)
    print(f"{len(collections)} collections for keyword IMERG:")
    for collection in collections:
        summary = value(collection, "summary")
        print(f"  {summary.get('short-name')}  v{summary.get('version')}")


if __name__ == "__main__":
    main()
