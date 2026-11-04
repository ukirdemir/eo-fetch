import json
from datetime import UTC, datetime

import pytest

from eo_fetch.backends.cds import CdsBackend, build_request, month_requests
from eo_fetch.backends.ecmwf import (
    EcmwfOpenDataBackend,
    cycles_between,
    item_key,
    parse_steps,
)
from eo_fetch.models import Query


def utc(*args):
    return datetime(*args, tzinfo=UTC)


class FakeEcmwfClient:
    def __init__(self):
        self.requests = []
        self.latest_args = None

    def latest(self, **kwargs):
        self.latest_args = kwargs
        return datetime(2026, 11, 3, 12)

    def retrieve(self, request, target):
        self.requests.append((request, target))


def ecmwf_with_client():
    backend = EcmwfOpenDataBackend()
    backend._client = FakeEcmwfClient()
    return backend


def test_parse_steps():
    assert parse_steps("0") == [0]
    assert parse_steps("0,6,12") == [0, 6, 12]
    assert parse_steps("0-24-6") == [0, 6, 12, 18, 24]
    with pytest.raises(ValueError, match="start-stop-by"):
        parse_steps("24-0-6")


def test_cycles_between_and_keys():
    cycles = cycles_between(utc(2026, 11, 1, 6), utc(2026, 11, 3), [0, 12])
    assert cycles == [utc(2026, 11, 1, 12), utc(2026, 11, 2, 0), utc(2026, 11, 2, 12)]
    assert item_key("oper", "fc", utc(2026, 11, 2, 12), 6, ["2t", "msl"]) == (
        "ifs_oper_fc_2026110212_006h_2t-msl.grib2"
    )


def test_ecmwf_search_plans_cycle_times_steps():
    backend = ecmwf_with_client()
    items = backend.search(
        Query(
            provider="p",
            product="oper",
            start=utc(2026, 11, 1),
            end=utc(2026, 11, 2),
            params={"param": "2t,msl", "steps": "0,6", "cycles": "00,12"},
        )
    )
    assert [i.key for i in items] == [
        "ifs_oper_fc_2026110100_000h_2t-msl.grib2",
        "ifs_oper_fc_2026110100_006h_2t-msl.grib2",
        "ifs_oper_fc_2026110112_000h_2t-msl.grib2",
        "ifs_oper_fc_2026110112_006h_2t-msl.grib2",
    ]
    assert items[1].time == utc(2026, 11, 1, 0)
    assert items[1].meta["step"] == "6"


def test_ecmwf_latest_cycle_without_time_range_and_limit():
    backend = ecmwf_with_client()
    items = backend.search(Query(provider="p", product="oper", params={"steps": "0-12-6"}))
    assert [i.time for i in items] == [utc(2026, 11, 3, 12)] * 3
    assert backend._client.latest_args == {"stream": "oper", "type": "fc", "step": 0}
    assert len(backend.search(Query(provider="p", product="oper", limit=1))) == 1


def test_ecmwf_fetch_builds_request(tmp_path):
    backend = ecmwf_with_client()
    item = backend.search(
        Query(
            provider="p",
            product="enfo",
            params={"param": "2t", "levtype": "sfc"},
        )
    )[0]
    backend.fetch(item, tmp_path / "f.grib2")
    request, target = backend._client.requests[0]
    assert request == {
        "date": 20261103,
        "time": 12,
        "step": 0,
        "stream": "enfo",
        "type": ["cf", "pf"],
        "param": ["2t"],
        "levtype": "sfc",
    }
    assert target.endswith("f.grib2")


def test_month_requests_partial_months():
    result = month_requests(utc(2026, 1, 30), utc(2026, 3, 2))
    assert result == [(2026, 1, [30, 31]), (2026, 2, list(range(1, 29))), (2026, 3, [1])]


def test_build_request_area_order_and_extra():
    request = build_request(
        year=2026,
        month=1,
        days=[1, 2],
        variables=["2m_temperature"],
        hours=["00:00"],
        bbox=(5.0, 47.0, 16.0, 55.0),
        data_format="grib",
        product_type="reanalysis",
        levels=["500"],
        extra={"download_format": "zip"},
    )
    assert request["area"] == [55.0, 5.0, 47.0, 16.0]  # N, W, S, E
    assert request["day"] == ["01", "02"] and request["month"] == "01"
    assert request["pressure_level"] == ["500"]
    assert request["download_format"] == "zip"


def test_cds_search_plans_months_and_fetches(tmp_path):
    calls = []

    class FakeCds:
        def retrieve(self, dataset, request, target):
            calls.append((dataset, request, target))

    backend = CdsBackend()
    backend._client = FakeCds()
    items = backend.search(
        Query(
            provider="p",
            product="reanalysis-era5-single-levels",
            start=utc(2026, 1, 15),
            end=utc(2026, 2, 3),
            bbox=(5.0, 47.0, 16.0, 55.0),
            params={"variable": "2m_temperature,total_precipitation"},
        )
    )
    assert [i.key for i in items] == [
        "reanalysis-era5-single-levels_202601_2m-temperature-total-precipitation.grib",
        "reanalysis-era5-single-levels_202602_2m-temperature-total-precipitation.grib",
    ]
    backend.fetch(items[1], tmp_path / "a.grib")
    dataset, request, target = calls[0]
    assert target.endswith("a.grib")
    assert dataset == "reanalysis-era5-single-levels"
    assert request["day"] == ["01", "02"]
    assert request["variable"] == ["2m_temperature", "total_precipitation"]
    assert json.loads(items[0].meta["request"])["time"] == ["00:00", "06:00", "12:00", "18:00"]


def test_cds_search_validation():
    backend = CdsBackend()
    base = {"provider": "p", "product": "d"}
    with pytest.raises(ValueError, match="--start and --end"):
        backend.search(Query(**base, params={"variable": "x"}))
    with pytest.raises(ValueError, match="variable="):
        backend.search(Query(**base, start=utc(2026, 1, 1), end=utc(2026, 1, 2)))
    with pytest.raises(ValueError, match="grib or netcdf"):
        backend.search(
            Query(
                **base,
                start=utc(2026, 1, 1),
                end=utc(2026, 1, 2),
                params={"variable": "x", "format": "csv"},
            )
        )


def test_cds_doctor_without_credentials(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert CdsBackend().doctor() is False
    assert "NOT FOUND" in capsys.readouterr().out
