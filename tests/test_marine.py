from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from eo_fetch.backends.marine import MarineBackend, subset_arguments, time_chunks
from eo_fetch.models import Query


def utc(*args):
    return datetime(*args, tzinfo=UTC)


class FakeToolbox:
    def __init__(self):
        self.calls = []

    def subset(
        self,
        dataset_id,
        variables=None,
        output_directory=None,
        output_filename=None,
        force_download=False,
        disable_progress_bar=False,
        **kwargs,
    ):
        self.calls.append(
            {
                "dataset_id": dataset_id,
                "variables": variables,
                "force_download": force_download,
                "kwargs": kwargs,
            }
        )
        (Path(output_directory) / output_filename).write_bytes(b"netcdf-bytes")

    def describe(self, contains):
        dataset = SimpleNamespace(dataset_id="cmems_x_P1D-m")
        return SimpleNamespace(
            products=[SimpleNamespace(title="Global ocean SST", datasets=[dataset, dataset])]
        )


def backend_with_toolbox():
    backend = MarineBackend()
    backend._cm = FakeToolbox()
    return backend


def test_time_chunks_cover_months_with_inclusive_ends():
    chunks = time_chunks(utc(2026, 1, 20), utc(2026, 3, 2))
    assert chunks == [
        (utc(2026, 1, 20), utc(2026, 1, 31, 23, 59, 59)),
        (utc(2026, 2, 1), utc(2026, 2, 28, 23, 59, 59)),
        (utc(2026, 3, 1), utc(2026, 3, 1, 23, 59, 59)),
    ]


def test_subset_arguments_adds_only_accepted_options():
    def new_toolbox(dataset_id, overwrite=False):
        return None

    def old_toolbox(dataset_id, force_download=False, disable_progress_bar=False):
        return None

    new = subset_arguments(new_toolbox, {"dataset_id": "d"}, Path("out"))
    old = subset_arguments(old_toolbox, {"dataset_id": "d"}, Path("out"))
    assert new["overwrite"] is True and "force_download" not in new
    assert old["force_download"] is True and old["disable_progress_bar"] is True
    assert new["output_directory"] == "out"


def test_search_plans_month_requests():
    backend = backend_with_toolbox()
    items = backend.search(
        Query(
            provider="p",
            product="cmems_x_P1D-m",
            start=utc(2026, 1, 20),
            end=utc(2026, 2, 3),
            bbox=(5.0, 50.0, 10.0, 55.0),
            params={"variables": "thetao,so", "max_depth": "10"},
        )
    )
    assert [i.key for i in items] == [
        "cmems_x_P1D-m_20260120-20260131_thetao-so.nc",
        "cmems_x_P1D-m_20260201-20260202_thetao-so.nc",
    ]
    assert "'maximum_depth': 10.0" in items[0].meta["request"]
    assert "'minimum_longitude': 5.0" in items[0].meta["request"]
    assert items[1].time == utc(2026, 2, 1)


def test_search_validation():
    backend = backend_with_toolbox()
    with pytest.raises(ValueError, match="--start and --end"):
        backend.search(Query(provider="p", product="d"))
    with pytest.raises(ValueError, match="--product"):
        backend.search(Query(provider="p"))


def test_fetch_writes_target_and_cleans_up(tmp_path):
    backend = backend_with_toolbox()
    item = backend.search(
        Query(
            provider="p",
            product="d",
            start=utc(2026, 1, 1),
            end=utc(2026, 1, 3),
            params={"variables": "thetao"},
        )
    )[0]
    target = tmp_path / "out.nc.part"
    backend.fetch(item, target)
    assert target.read_bytes() == b"netcdf-bytes"
    assert not (tmp_path / "out.nc.part.dl").exists()
    call = backend._cm.calls[0]
    assert call["dataset_id"] == "d" and call["variables"] == ["thetao"]
    assert call["force_download"] is True
    assert call["kwargs"]["start_datetime"] == "2026-01-01T00:00:00"
    assert call["kwargs"]["end_datetime"] == "2026-01-02T23:59:59"


def test_collections_lists_unique_dataset_ids():
    backend = backend_with_toolbox()
    assert backend.collections("sst") == [("cmems_x_P1D-m", "Global ocean SST")]
    with pytest.raises(ValueError, match="--text"):
        backend.collections("")
