import pytest

import eo_fetch as eof
from eo_fetch.catalog.descriptions import PRODUCT_NOTES, describe_alias
from eo_fetch.cli import main, product_hint
from eo_fetch.discovery import alias_matches, find_products, suggest
from eo_fetch.registry import all_providers, get_provider


class FakeBackend:
    def __init__(self, collections=None, folders=None, fail=False):
        self._collections = collections or []
        self.folders_seen = folders or []
        self.fail = fail

    def collections(self, text):
        if self.fail:
            raise RuntimeError("no credentials")
        return self._collections

    def search(self, query):
        return []


def test_every_alias_has_a_description_and_none_is_orphaned():
    aliases = {f"{info.name}/{alias}" for info in all_providers() for alias in info.products}
    assert aliases - set(PRODUCT_NOTES) == set(), "aliases without a description"
    assert set(PRODUCT_NOTES) - aliases == set(), "descriptions without an alias"


def test_describe_alias():
    assert "radar" in describe_alias("dwd", "radolan-yw").lower()
    assert describe_alias("dwd", "nonsense") == ""


def test_alias_matches_need_every_word():
    info = get_provider("nasa")
    names = [m.product for m in alias_matches(info, ["imerg", "daily"])]
    assert "imerg-late-daily" in names and "imerg-final-halfhourly" not in names
    assert alias_matches(info, ["no-such-thing"]) == []
    assert len(alias_matches(info, [])) == len(info.products)


def test_find_products_across_providers_by_description_and_provider_name():
    def offline(info, params):
        raise AssertionError("no network without text and live")

    found = find_products("radar rain", make_backend=offline)
    assert {m.provider for m in found} >= {"dwd"}
    assert all(m.source == "alias" for m in found)
    only = find_products("", "esgf", browse=False, live=False, make_backend=offline)
    assert [m.product for m in only] == [
        "cmip3",
        "cmip5",
        "cmip6",
        "cmip7",
        "cordex-cmip6",
        "input4mips",
        "obs4mips",
    ]


def test_live_catalogue_adds_unknown_collections_only():
    backend = FakeBackend([("NEW_ID", "A new collection"), ("GPM_3IMERGDL", "already an alias")])
    found = find_products("precipitation", "nasa", make_backend=lambda i, p: backend)
    live = [m for m in found if m.source == "catalogue"]
    assert [(m.product, m.description) for m in live] == [("NEW_ID", "A new collection")]
    assert any(m.source == "alias" for m in found)


def test_live_is_off_for_all_providers_unless_asked():
    calls = []

    def make(info, params):
        calls.append(info.name)
        return FakeBackend([("X", "x")])

    find_products("precipitation", make_backend=make)
    assert calls == []
    find_products("precipitation", live=True, make_backend=make)
    assert "nasa" in calls and "eumetsat" in calls


def test_unreachable_catalogue_is_reported_not_raised():
    errors = []
    found = find_products(
        "precipitation",
        "nasa",
        make_backend=lambda i, p: FakeBackend(fail=True),
        on_error=lambda info, error: errors.append((info.name, str(error))),
    )
    assert errors == [("nasa", "no credentials")]
    assert any(m.source == "alias" for m in found)  # aliases are still listed


def test_file_tree_provider_lists_top_level_folders():
    backend = FakeBackend(folders=["weather", "climate_environment"])
    found = find_products("", "dwd", make_backend=lambda i, p: backend)
    folders = [m.product for m in found if m.source == "folder"]
    assert folders == ["weather", "climate_environment"]


def test_suggest_close_names_only_for_unknown_products():
    info = get_provider("dwd")
    assert "radolan-yw" in suggest(info, "radolan-yy")
    assert suggest(info, "radolan-yw") == []
    assert suggest(info, "weather/radar/radolan/yw") == []
    assert suggest(info, "") == []
    assert suggest(info, "zzzzzzzz") == []


def test_product_hint_prints_suggestions_and_stays_quiet_for_known_products(capsys):
    info = get_provider("dwd")
    product_hint(info, "radolan-yy", [])
    printed = capsys.readouterr().out
    assert "Did you mean: radolan-yw" in printed and "eo-fetch products --provider dwd" in printed
    product_hint(info, "radolan-yw", [])
    assert capsys.readouterr().out == ""
    product_hint(get_provider("local"), "", [])
    assert capsys.readouterr().out == ""


def test_unexpected_errors_are_short_unless_debug(monkeypatch, capsys):
    from eo_fetch import cli

    def boom(args):
        raise TypeError("bad input")

    monkeypatch.setattr(cli, "cmd_providers", boom)
    assert main(["providers"]) == 1
    err = capsys.readouterr().err
    assert "error: TypeError: bad input" in err and "--debug" in err and "Traceback" not in err
    with pytest.raises(TypeError):
        main(["--debug", "providers"])


def test_library_warnings_lose_their_file_paths_and_the_format_is_restored(monkeypatch):
    import warnings

    from eo_fetch import cli

    original = warnings.formatwarning
    seen = []

    def noisy(args):
        seen.append(warnings.formatwarning("careful", UserWarning, "lib/catalog.py", 3))
        return 0

    monkeypatch.setattr(cli, "cmd_providers", noisy)
    assert main(["providers"]) == 0
    assert seen == ["warning: careful\n"]
    assert warnings.formatwarning is original
    main(["--debug", "providers"])
    assert "lib/catalog.py" in seen[1]


def test_run_search_hints_before_reraising(capsys):
    from eo_fetch.cli import run_search

    class Broken:
        def search(self, query):
            raise FileNotFoundError("Not found")

    with pytest.raises(FileNotFoundError):
        run_search(get_provider("dwd"), Broken(), None, "radolan-yy")
    assert "Did you mean: radolan-yw" in capsys.readouterr().out


def test_backend_advice_for_empty_results(capsys):
    from eo_fetch.backends.esgf import EsgfBackend
    from eo_fetch.cli import empty_hint

    empty_hint(EsgfBackend(), [])
    assert "indices=all" in capsys.readouterr().out
    empty_hint(EsgfBackend(), [object()])
    assert capsys.readouterr().out == ""
    empty_hint(FakeBackend(), [])
    assert capsys.readouterr().out == ""


def test_folder_and_catalogue_lines_are_formatted_cleanly(monkeypatch, capsys):
    from eo_fetch import cli
    from eo_fetch.discovery import ProductMatch

    shown = [
        ProductMatch("dwd", "weather", "", "folder"),
        ProductMatch("nasa", "X1", "A live collection", "catalogue"),
    ]
    monkeypatch.setattr(cli, "products", lambda *args, **kwargs: shown)
    assert main(["products"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "dwd/weather  [folder]"
    assert lines[1] == "nasa/X1      A live collection [catalogue]"


def test_cli_products_lists_and_filters(capsys):
    assert main(["products", "lightning"]) == 0
    printed = capsys.readouterr().out
    assert "eumetsat/mtg-lightning-flashes" in printed and "noaa/goes19-lightning" in printed
    assert "products. Use: eo-fetch search" in printed
    assert main(["products", "--limit", "2", "radar"]) == 0
    assert "2 of " in capsys.readouterr().out
    assert main(["products", "zzzzzz-nothing"]) == 0
    assert "No products match" in capsys.readouterr().out


def test_python_api_products():
    found = eof.products("precipitation", "nasa", live=False)
    assert "imerg-late-daily" in [m.product for m in found]
    assert isinstance(found[0], eof.ProductMatch)
    with pytest.raises(KeyError):
        eof.products(provider="no-such-provider")
