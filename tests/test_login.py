from pathlib import Path

import pytest

from eo_fetch.backends.cds import CdsBackend
from eo_fetch.backends.credentials import ask_secret, confirm_overwrite
from eo_fetch.backends.eumetsat import EumetsatBackend, load_credentials


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_cds_login_writes_rc_file_and_does_not_print_the_key(home, monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt: "  secret-token-123 ")
    CdsBackend().login()
    text = (home / ".cdsapirc").read_text()
    assert text == "url: https://cds.climate.copernicus.eu/api\nkey: secret-token-123\n"
    assert "secret-token-123" not in capsys.readouterr().out


def test_cds_login_keeps_existing_file_unless_confirmed(home, monkeypatch):
    rc = home / ".cdsapirc"
    rc.write_text("old")
    monkeypatch.setattr("getpass.getpass", lambda prompt: "new")
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    CdsBackend().login()
    assert rc.read_text() == "old"
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    CdsBackend().login()
    assert "key: new" in rc.read_text()


def test_eumetsat_login_roundtrip(home, monkeypatch, capsys):
    monkeypatch.delenv("EUMETSAT_KEY", raising=False)
    monkeypatch.delenv("EUMETSAT_SECRET", raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt: "consumer-key")
    monkeypatch.setattr("getpass.getpass", lambda prompt: "consumer-secret")
    EumetsatBackend().login()
    assert load_credentials() == ("consumer-key", "consumer-secret")
    assert "consumer-secret" not in capsys.readouterr().out


def test_empty_secret_is_rejected(monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda prompt: "   ")
    with pytest.raises(ValueError, match="Nothing entered"):
        ask_secret("x: ")


def test_confirm_overwrite_for_missing_file(tmp_path):
    assert confirm_overwrite(tmp_path / "missing") is True
