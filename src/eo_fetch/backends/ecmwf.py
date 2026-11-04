"""ECMWF Open Data backend: forecast fields by parameter and lead time (no account needed).

There is no file listing to search: ``search`` plans one download per forecast cycle and lead
time, and ``fetch`` retrieves just the requested parameters with the ecmwf-opendata client.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from eo_fetch.models import Item, Query


def split_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_steps(text: str) -> list[int]:
    """Lead times in hours: ``0,6,12`` or a range ``0-48-6`` (start-stop-by, stop included)."""
    if "-" in text and "," not in text:
        start, stop, *rest = (int(part) for part in text.split("-"))
        by = rest[0] if rest else 1
        if by <= 0 or stop < start:
            raise ValueError(f"Invalid steps {text!r}: use start-stop-by with by > 0")
        return list(range(start, stop + 1, by))
    return [int(part) for part in split_list(text)]


def cycles_between(start: datetime, end: datetime, hours: list[int]) -> list[datetime]:
    """Forecast start times at the given hours in [start, end)."""
    day = datetime(start.year, start.month, start.day, tzinfo=UTC)
    found = []
    while day < end:
        for hour in sorted(hours):
            cycle = day + timedelta(hours=hour)
            if start <= cycle < end:
                found.append(cycle)
        day += timedelta(days=1)
    return found


def item_key(stream: str, kind: str, cycle: datetime, step: int, params: list[str]) -> str:
    return f"ifs_{stream}_{kind}_{cycle:%Y%m%d%H}_{step:03d}h_{'-'.join(params)}.grib2"


class EcmwfOpenDataBackend:
    """Plan and fetch ECMWF Open Data forecasts.

    ``query.product`` is the stream: ``oper`` (high-resolution forecast) or ``enfo`` (ensemble).
    Search parameters: ``param`` (default ``2t``), ``steps`` (hours; default ``0``; ``0,6,12`` or
    ``0-48-6``), ``cycles`` (forecast hours, default ``00,12``), ``type`` (default ``fc`` for
    oper, ``cf,pf`` for enfo), ``levtype`` and ``levelist`` to select levels. Without a time
    range, the latest available cycle is used. ``source`` chooses the mirror: ``ecmwf``, ``aws``,
    ``azure`` or ``google``.
    """

    name = "ecmwf-opendata"
    max_connections = 2
    query_params = frozenset({"param", "steps", "cycles", "type", "levtype", "levelist"})

    def __init__(self, source: str = "ecmwf", resol: str = "0p25") -> None:
        self.source = source
        self.resol = resol
        self._client = None

    def client(self):
        if self._client is None:
            from ecmwf.opendata import Client

            self._client = Client(source=self.source, resol=self.resol)
        return self._client

    def search(self, query: Query) -> list[Item]:
        stream = query.product or "oper"
        params = split_list(query.params.get("param") or "2t")
        steps = parse_steps(query.params.get("steps") or "0")
        hours = [int(h) for h in split_list(query.params.get("cycles") or "00,12")]
        kind = query.params.get("type") or ("fc" if stream == "oper" else "cf,pf")
        if query.start or query.end:
            start = query.start or query.end - timedelta(days=1)
            end = query.end or start + timedelta(days=1)
            cycles = cycles_between(start, end, hours)
        else:
            latest = self.client().latest(stream=stream, type=kind.split(",")[0], step=steps[0])
            cycles = [latest.replace(tzinfo=UTC)]
        items = []
        for cycle in cycles:
            for step in steps:
                meta = {
                    "date": f"{cycle:%Y%m%d}",
                    "time": str(cycle.hour),
                    "step": str(step),
                    "stream": stream,
                    "type": kind,
                    "param": ",".join(params),
                }
                for key in ("levtype", "levelist"):
                    if query.params.get(key):
                        meta[key] = query.params[key]
                items.append(
                    Item(
                        provider=query.provider,
                        product=stream,
                        key=item_key(stream, kind.replace(",", ""), cycle, step, params),
                        time=cycle,
                        meta=meta,
                    )
                )
        return items[: query.limit] if query.limit else items

    def fetch(self, item: Item, target: Path) -> None:
        meta = dict(item.meta)
        request = {
            "date": int(meta["date"]),
            "time": int(meta["time"]),
            "step": int(meta["step"]),
            "stream": meta["stream"],
            "type": split_list(meta["type"]),
            "param": split_list(meta["param"]),
        }
        for key in ("levtype", "levelist"):
            if key in meta:
                request[key] = split_list(meta[key]) if key == "levelist" else meta[key]
        self.client().retrieve(request=request, target=str(target))

    def doctor(self, collection_ids: tuple[str, ...] = ()) -> bool:
        try:
            latest = self.client().latest(stream="oper", type="fc", step=0)
        except Exception as error:
            print(f"  latest cycle: FAILED ({type(error).__name__}: {error})")
            print("  (try --param source=aws if the ECMWF portal is busy)")
            return False
        print(f"  source {self.source}: latest oper cycle {latest:%Y-%m-%d %H}Z")
        return True
