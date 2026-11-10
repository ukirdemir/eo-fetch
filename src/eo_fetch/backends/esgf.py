"""ESGF backend: climate-model data (CMIP6, CMIP7, CORDEX, ...) found with intake-esgf.

ESGF is changing its search technology (the old Solr indices are being retired in favour of
Globus and STAC indices), so the searching is left to ``intake-esgf``, which follows those
changes. ``search`` asks it for the files of every matching dataset; ``fetch`` downloads a file
over HTTPS from the first mirror that works, and the normal eo-fetch downloader checks size
and checksum.
"""

from __future__ import annotations

import contextlib
import re
import warnings
from datetime import UTC, datetime
from pathlib import Path

from eo_fetch import __version__
from eo_fetch.models import Item, Query

USER_AGENT = f"eo-fetch/{__version__}"
INDEX_NAME = re.compile(r"\w*ESGFIndex\('([^']+)'")
NO_ANSWER = "failed to return a response"
SOLR_NOTICE = "old Solr technology"
DIGEST_LENGTHS = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}
MULTIHASH_SHA256 = "1220"  # prefix of a hex multihash holding a SHA-256 digest

_truststore_injected = False


def split_values(text: str) -> str | list[str]:
    """``"tas"`` stays a string; ``"tas,pr"`` becomes a list."""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    return parts if len(parts) > 1 else (parts[0] if parts else "")


def normalise_checksum(value: object, kind: object) -> str | None:
    """Return ``"<algorithm>:<hex>"`` for a checksum hashlib can verify, else None."""
    if not value:
        return None
    text = str(value).strip().lower()
    algorithm = re.sub(r"[^a-z0-9]", "", str(kind or "").lower())
    if ":" in text:
        algorithm, _, text = text.partition(":")
        algorithm = re.sub(r"[^a-z0-9]", "", algorithm)
    if len(text) == len(MULTIHASH_SHA256) + 64 and text.startswith(MULTIHASH_SHA256):
        algorithm, text = "sha256", text[len(MULTIHASH_SHA256) :]
    if algorithm not in DIGEST_LENGTHS or len(text) != DIGEST_LENGTHS[algorithm]:
        return None
    if not re.fullmatch(r"[0-9a-f]+", text):
        return None
    return f"{algorithm}:{text}"


def to_datetime(value: object) -> datetime | None:
    if value is None or value != value:  # None or NaT/NaN
        return None
    try:
        moment = value.to_pydatetime()  # pandas Timestamp
    except AttributeError:
        moment = value
    if not isinstance(moment, datetime):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def item_from_info(provider: str, project: str, info: dict) -> Item | None:
    """An Item for one file-info record of intake-esgf, or None if it has no HTTPS link."""
    links = [link for link in info.get("HTTPServer") or [] if link]
    if not links:
        return None
    size = info.get("size")
    return Item(
        provider=provider,
        product=project,
        key=Path(str(info["path"])).name,
        time=to_datetime(info.get("file_start")),
        size=int(size) if size else None,
        url=links[0],
        checksum=normalise_checksum(info.get("checksum"), info.get("checksum_type")),
        meta={"mirrors": " ".join(links), "dataset": str(info.get("key", ""))},
    )


def index_settings(indices: str) -> dict:
    """intake-esgf configuration for an ``indices`` option (see the user manual)."""
    settings: dict = {}
    chosen = {}
    for part in indices.split(","):
        name = part.strip()
        if name.lower() == "all":
            settings["all_indices"] = True
        elif name:
            chosen[name.lstrip("-")] = not name.startswith("-")
    if chosen:
        settings["indices"] = chosen
    return settings


def known_indices(conf) -> set[str]:
    """Names of every index intake-esgf knows (empty if its configuration cannot be read)."""
    try:
        return {name for kind in ("stac", "globus", "solr") for name in conf[f"{kind}_indices"]}
    except (KeyError, TypeError):
        return set()


@contextlib.contextmanager
def index_notes(dead: set[str]):
    """Collect intake-esgf's per-index warnings: remember silent indices, pass others on."""
    caught: list = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            yield
    finally:
        for entry in caught:
            text = str(entry.message)
            found = INDEX_NAME.search(text)
            if NO_ANSWER in text and found:
                dead.add(found.group(1))
            elif SOLR_NOTICE not in text:
                warnings.warn_explicit(entry.message, entry.category, entry.filename, entry.lineno)


class EsgfBackend:
    """Search and download ESGF files through intake-esgf.

    ``query.product`` is the project (CMIP6, CMIP7, CORDEX-CMIP6, CMIP5, ...; default:
    intake-esgf's default). Every ``--param`` is an ESGF facet, for example
    ``variable_id=tas``, ``experiment_id=historical``, ``source_id=CanESM5``,
    ``member_id=r1i1p1f1``, ``table_id=Amon``, ``frequency=mon``; a comma separates
    alternatives. ``--start`` and ``--end`` keep only files overlapping that period. ``--text``
    is a free-text search. ``--param indices=...`` chooses the search indices (see
    :func:`index_settings`; ``indices=all`` finds older projects). Narrow the search: every
    matching dataset is asked for its files.
    """

    name = "esgf"
    max_connections = 4
    query_params: frozenset[str] = frozenset()
    open_params = True  # any --param is an ESGF facet, except the constructor's own
    empty_result_hint = (
        "Nothing found. Facet names and values must match the project (CMIP6: variable_id, "
        "experiment_id, source_id, ...; CMIP5: variable, experiment, model, ensemble, ...). "
        "Older projects such as CMIP5 are only in the legacy indices: add --param indices=all "
        "(slower)."
    )

    def __init__(self, indices: str = "") -> None:
        self.indices = indices
        self._catalog = None
        self._session = None
        self._dead: set[str] = set()

    def catalog(self):
        if self._catalog is None:
            import intake_esgf

            settings = index_settings(self.indices)
            known = known_indices(intake_esgf.conf)
            unknown = sorted(set(settings.get("indices", {})) - known) if known else []
            if unknown:
                raise ValueError(
                    f"Unknown ESGF index {', '.join(unknown)}. Known: {', '.join(sorted(known))}"
                )
            # all_indices is applied after the per-index flags, so it needs a step of its own
            with index_notes(self._dead), contextlib.ExitStack() as stack:
                if settings.get("all_indices"):
                    stack.enter_context(intake_esgf.conf.set(all_indices=True))
                if settings.get("indices"):
                    stack.enter_context(intake_esgf.conf.set(indices=settings["indices"]))
                self._catalog = intake_esgf.ESGFCatalog()
        return self._catalog

    def report_dead_indices(self) -> None:
        """One short note for the indices that did not answer (instead of one warning each)."""
        if not self._dead:
            return
        names, self._dead = sorted(self._dead), set()
        skip = ",".join(filter(None, [self.indices.strip(), *(f"-{name}" for name in names)]))
        warnings.warn(
            f"ESGF: no answer from {', '.join(names)}; results may be incomplete. "
            f'To skip it: --param "indices={skip}"',
            UserWarning,
            stacklevel=2,
        )

    def session(self):
        """A requests session using the system certificates."""
        global _truststore_injected
        if self._session is None:
            import requests

            if not _truststore_injected:
                try:
                    import truststore

                    truststore.inject_into_ssl()
                except ImportError:
                    pass
                _truststore_injected = True
            self._session = requests.Session()
            self._session.headers["User-Agent"] = USER_AGENT
        return self._session

    def search(self, query: Query) -> list[Item]:
        try:
            return self._search(query)
        finally:
            self.report_dead_indices()

    def _search(self, query: Query) -> list[Item]:
        if query.bbox:
            raise ValueError(
                "ESGF files are global model output: --bbox is not supported here; "
                "crop after downloading"
            )
        facets: dict = {}
        if query.product:
            facets["project"] = query.product
        for key, value in query.params.items():
            if value and key != "indices":  # "indices" configures the backend, it is no facet
                facets[key] = split_values(value)
        if not facets and not query.text:
            raise ValueError("Give at least one facet with --param (for example variable_id=tas)")
        catalog = self.catalog()
        extra: dict = {}
        if query.start:
            extra["file_start"] = query.start.strftime("%Y-%m-%d %H:%M:%S")
        if query.end:
            extra["file_end"] = query.end.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with index_notes(self._dead):
                catalog.search(query=query.text, quiet=True, **extra, **facets)
        except Exception as error:
            if type(error).__name__ == "NoSearchResults":
                return []
            raise
        try:
            with index_notes(self._dead):
                infos = catalog._get_file_info(quiet=True)
        except AttributeError as error:
            raise RuntimeError(
                "This version of intake-esgf has no file listing eo-fetch can use; "
                "try `pip install -U intake-esgf`"
            ) from error
        project = str(facets.get("project") or "")
        items = []
        seen = set()
        for info in infos:
            item = item_from_info(query.provider, project, info)
            if item is None or item.key in seen:
                continue
            seen.add(item.key)
            items.append(item)
        floor = datetime.min.replace(tzinfo=UTC)
        items.sort(key=lambda item: (item.time or floor, item.key))
        return items[: query.limit] if query.limit else items

    def fetch(self, item: Item, target: Path) -> None:
        mirrors = (item.meta.get("mirrors") or item.url or "").split()
        if not mirrors:
            raise ValueError(f"No download link for {item.key}")
        last_error: Exception | None = None
        for url in mirrors:
            try:
                with self.session().get(url, stream=True, timeout=(15, 120)) as response:
                    response.raise_for_status()
                    with target.open("wb") as out:
                        for chunk in response.iter_content(1024 * 1024):
                            out.write(chunk)
                return
            except Exception as error:
                last_error = error
        raise OSError(f"All {len(mirrors)} mirrors failed for {item.key}: {last_error}")

    def doctor(self, collection_ids: tuple[str, ...] = ()) -> bool:
        try:
            catalog = self.catalog()
            names = ", ".join(type(index).__name__ for index in catalog.indices)
            print(f"  intake-esgf ready; search indices: {names}")
        except Exception as error:
            print(f"  intake-esgf: FAILED ({type(error).__name__}: {error})")
            return False
        print("  downloads need no login for open CMIP data; some nodes may still ask for one")
        return True
