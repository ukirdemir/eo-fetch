"""Tests for the downloader, manifests, registry and CLI, using the local backend and fakes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eo_fetch.backends import get_backend
from eo_fetch.cli import main, parse_params, parse_time
from eo_fetch.download import download_items, matches
from eo_fetch.manifest import build_manifest, verify_manifest, write_manifest
from eo_fetch.models import Item, Query
from eo_fetch.providers import get_provider


def make_files(root: Path, names: list[str]) -> None:
    for name in names:
        (root / name).write_text(f"content of {name}")


def no_sleep(_seconds: float) -> None:
    return None


class FlakyBackend:
    """Fails the first ``failures`` fetches of every item, then writes the payload."""

    name = "flaky"
    max_connections = 2

    def __init__(self, failures: int = 2, payload: bytes = b"data") -> None:
        self.failures = failures
        self.payload = payload
        self.calls: dict[str, int] = {}

    def search(self, query: Query) -> list[Item]:
        return []

    def fetch(self, item: Item, target: Path) -> None:
        self.calls[item.key] = self.calls.get(item.key, 0) + 1
        if self.calls[item.key] <= self.failures:
            target.write_bytes(self.payload[:2])  # a truncated file must never survive
            raise ConnectionError("connection reset")
        target.write_bytes(self.payload)


class CountingBackend:
    """Records how many fetches run at the same time."""

    name = "counting"

    def __init__(self, max_connections: int) -> None:
        import threading

        self.max_connections = max_connections
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def search(self, query: Query) -> list[Item]:
        return []

    def fetch(self, item: Item, target: Path) -> None:
        import time

        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.05)
        target.write_bytes(b"x")
        with self.lock:
            self.active -= 1


def test_item_filename_is_safe():
    item = Item("p", "prod", "a/b/..:weird name?.nc")
    assert item.filename == "weird_name_.nc"


def test_local_search_filters_and_limits(tmp_path: Path):
    make_files(tmp_path, ["a.nc", "b.nc", "c.txt"])
    backend = get_backend("local", {"root": str(tmp_path)})
    items = backend.search(Query(provider="local", text="*.nc"))
    assert [item.key for item in items] == ["a.nc", "b.nc"]
    assert len(backend.search(Query(provider="local", text="*", limit=1))) == 1
    future = datetime(2100, 1, 1, tzinfo=UTC)
    assert backend.search(Query(provider="local", start=future)) == []


def test_download_resumes_and_skips(tmp_path: Path):
    source, dest = tmp_path / "src", tmp_path / "dest"
    source.mkdir()
    make_files(source, ["a.nc", "b.nc"])
    backend = get_backend("local", {"root": str(source)})
    items = backend.search(Query(provider="local"))
    first = download_items(backend, items, dest, sleep=no_sleep)
    assert [r.status for r in first] == ["downloaded", "downloaded"]
    again = download_items(backend, items, dest, sleep=no_sleep)
    assert [r.status for r in again] == ["skipped", "skipped"]
    assert not list(dest.glob("*.part"))


def test_retries_then_succeeds_without_truncated_files(tmp_path: Path):
    backend = FlakyBackend(failures=2)
    item = Item("flaky", "p", "x.nc", size=4)
    [result] = download_items(backend, [item], tmp_path, retries=3, sleep=no_sleep)
    assert result.status == "downloaded"
    assert (tmp_path / "x.nc").read_bytes() == b"data"
    assert not list(tmp_path.glob("*.part"))


def test_gives_up_after_retries_and_reports_error(tmp_path: Path):
    backend = FlakyBackend(failures=10)
    [result] = download_items(
        backend, [Item("flaky", "p", "x.nc")], tmp_path, retries=2, sleep=no_sleep
    )
    assert result.status == "failed"
    assert "ConnectionError" in result.error
    assert not list(tmp_path.iterdir())


def test_checksum_mismatch_is_rejected(tmp_path: Path):
    good = "sha256:" + hashlib.sha256(b"data").hexdigest()
    ok = Item("flaky", "p", "ok.nc", checksum=good)
    bad = Item("flaky", "p", "bad.nc", checksum="sha256:" + "0" * 64)
    results = download_items(FlakyBackend(failures=0), [ok, bad], tmp_path, retries=1)
    assert [r.status for r in results] == ["downloaded", "failed"]
    assert matches(tmp_path / "ok.nc", ok)
    assert not (tmp_path / "bad.nc").exists()


def test_never_exceeds_backend_connection_limit(tmp_path: Path):
    backend = CountingBackend(max_connections=2)
    items = [Item("c", "p", f"{i}.nc") for i in range(8)]
    download_items(backend, items, tmp_path, workers=8)
    assert backend.peak <= 2


def test_manifest_roundtrip_and_verify(tmp_path: Path):
    source, dest = tmp_path / "src", tmp_path / "dest"
    source.mkdir()
    make_files(source, ["a.nc"])
    backend = get_backend("local", {"root": str(source)})
    query = Query(provider="local", text="*.nc")
    results = download_items(backend, backend.search(query), dest)
    manifest_path = dest / "manifest.json"
    write_manifest(manifest_path, build_manifest(query, get_provider("local"), results))
    data = json.loads(manifest_path.read_text())
    assert data["files"][0]["sha256"] == hashlib.sha256(b"content of a.nc").hexdigest()
    assert verify_manifest(manifest_path, dest) == []
    (dest / "a.nc").write_text("tampered")
    assert "size differs" in verify_manifest(manifest_path, dest)[0]


def test_parse_helpers():
    assert parse_time("2026-09-01").tzinfo is not None
    assert parse_params(["a=1", "b=x=y"]) == {"a": "1", "b": "x=y"}
    with pytest.raises(SystemExit):
        parse_params(["novalue"])


def test_cli_providers_search_download_verify(tmp_path: Path, capsys):
    source, dest = tmp_path / "src", tmp_path / "dest"
    source.mkdir()
    make_files(source, ["a.nc", "b.nc"])
    common = ["--provider", "local", "--param", f"root={source}", "--text", "*.nc"]

    assert main(["providers"]) == 0
    assert "local" in capsys.readouterr().out
    assert main(["search", *common]) == 0
    assert "2 items" in capsys.readouterr().out
    assert main(["download", *common, "--dest", str(dest), "--dry-run"]) == 0
    assert not dest.exists()
    assert main(["download", *common, "--dest", str(dest)]) == 0
    assert (dest / "manifest.json").is_file()
    assert main(["verify", str(dest / "manifest.json"), "--root", str(dest)]) == 0


def test_cli_unknown_provider_is_a_clean_error(capsys):
    assert main(["search", "--provider", "nope"]) == 2
    assert "Unknown provider" in capsys.readouterr().err
