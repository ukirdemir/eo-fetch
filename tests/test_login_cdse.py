from pathlib import Path

import pytest

from eo_fetch.backends.stac import StacBackend, cdse_file, cdse_keys

CDSE = {"catalog_url": "https://stac.example", "s3_endpoint": "https://s3.example"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CDSE_S3_KEY", raising=False)
    monkeypatch.delenv("CDSE_S3_SECRET", raising=False)
    return tmp_path


def test_login_writes_private_file_and_hides_the_secret(home, monkeypatch, capsys):
    answers = iter(["access-key", "very-secret"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    StacBackend(**CDSE).login()
    assert cdse_file().read_text(encoding="utf-8").strip() == "access-key,very-secret"
    assert cdse_keys() == (("access-key", "very-secret"), str(cdse_file()))
    output = capsys.readouterr().out
    assert "very-secret" not in output and "access-key" not in output


def test_environment_wins_over_file(home, monkeypatch):
    cdse_file().parent.mkdir(parents=True)
    cdse_file().write_text("file-key,file-secret", encoding="utf-8")
    monkeypatch.setenv("CDSE_S3_KEY", "env-key")
    monkeypatch.setenv("CDSE_S3_SECRET", "env-secret")
    assert cdse_keys() == (("env-key", "env-secret"), "environment")


def test_file_written_by_powershell_with_bom_is_read(home):
    cdse_file().parent.mkdir(parents=True)
    cdse_file().write_bytes(b"\xef\xbb\xbfkey,secret\r\n")
    assert cdse_keys()[0] == ("key", "secret")


def test_missing_or_incomplete_file_means_no_keys(home):
    assert cdse_keys() == (None, "")
    cdse_file().parent.mkdir(parents=True)
    cdse_file().write_text("only-a-key", encoding="utf-8")
    assert cdse_keys() == (None, "")


def test_catalogue_without_s3_needs_no_login(home, capsys):
    StacBackend(catalog_url="https://stac.example").login()
    assert "needs no login" in capsys.readouterr().out
    assert not cdse_file().exists()
