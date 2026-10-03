"""Read-only client for the MusicBrainz web service.

The MusicBrainz API asks clients to identify themselves with a User-Agent and
to limit requests to one per second. This module keeps the calls together and
caches the results per artist name.
"""

from __future__ import annotations

import time
from typing import NotRequired, TypedDict

import requests

from beets_flask.config import get_config
from beets_flask.logger import log

#: Minimum interval between MusicBrainz requests (they ask for 1 req/s).
RATE_LIMIT_SECONDS = 1.0

#: How long to remember search results for an artist name.
CACHE_TTL_SECONDS = 24 * 60 * 60


class ArtistMatch(TypedDict):
    name: str
    mbid: str
    sort_name: NotRequired[str]
    disambiguation: NotRequired[str]
    type: NotRequired[str]
    begin_date: NotRequired[str]
    country: NotRequired[str]
    score: NotRequired[int]


class ReleaseMatch(TypedDict):
    #: MusicBrainz release group id (the ``mb_albumid`` of a beets album).
    mbid: str
    title: str
    artist: str
    score: NotRequired[int]


_cache: dict[str, tuple[float, list[ArtistMatch] | list[ReleaseMatch]]] = {}
_last_request_at: float = 0.0


def _ws_url() -> str:
    config = get_config()
    return config["gui"]["musicbrainz"]["ws_url"].get(str)  # type: ignore


def _user_agent() -> str:
    config = get_config()
    return config["gui"]["musicbrainz"]["user_agent"].get(str)  # type: ignore


def _check_artists_enabled() -> bool:
    config = get_config()
    return bool(config["gui"]["musicbrainz"]["check_artists"].get(bool))  # type: ignore


def _rate_limit() -> None:
    """Sleep so requests are at least one second apart."""
    global _last_request_at
    now = time.monotonic()
    wait = RATE_LIMIT_SECONDS - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _search_query(name: str) -> str:
    """Return a quoted Lucene phrase for an artist name."""
    return f'artist:"{name.replace(chr(34), "")}"'


def _request_artists(name: str) -> list[ArtistMatch] | None:
    """Search the web service for an artist.

    Returns the top matches (sorted by MusicBrainz score) or None when the
    lookup could not be performed (lookup disabled, network error, bad
    response).
    """
    if not _check_artists_enabled():
        return None

    url = f"{_ws_url()}/ws/2/artist"
    params = {"query": _search_query(name), "fmt": "json", "limit": "5"}
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}

    _rate_limit()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        log.debug(f"MusicBrainz artist search failed for {name!r}: {e}")
        return None

    try:
        payload = response.json()
    except ValueError as e:
        log.debug(f"MusicBrainz artist search returned invalid json: {e}")
        return None

    matches: list[ArtistMatch] = []
    for raw in payload.get("artists", []) or []:
        match: ArtistMatch = {
            "name": raw.get("name") or "",
            "mbid": raw.get("id") or "",
        }
        if raw.get("sort-name"):
            match["sort_name"] = raw["sort-name"]
        if raw.get("disambiguation"):
            match["disambiguation"] = raw["disambiguation"]
        if raw.get("type"):
            match["type"] = raw["type"]
        if raw.get("begin"):
            match["begin_date"] = raw["begin"]
        if raw.get("country"):
            match["country"] = raw["country"]
        score = raw.get("score")
        if score is not None:
            match["score"] = int(score)
        matches.append(match)
    return matches


def search_artist(name: str) -> list[ArtistMatch] | None:
    """Look up an artist by name, caching the results.

    Returns the top matches or None when the lookup is not possible.
    """
    key = name.strip().lower()
    cached = _cache.get(key)
    if cached is not None:
        created_at, matches = cached
        if time.monotonic() - created_at < CACHE_TTL_SECONDS:
            return matches
        del _cache[key]

    matches = _request_artists(name)
    if matches is not None:
        _cache[key] = (time.monotonic(), matches)
    return matches


def _request_releases_by_barcode(barcode: str) -> list[ReleaseMatch] | None:
    """Search the web service for releases with the given barcode.

    Returns the top matches or None when the lookup could not be performed
    (lookup disabled, network error, bad response).
    """
    if not _check_artists_enabled():
        return None

    url = f"{_ws_url()}/ws/2/release"
    params = {
        "query": f'barcode:"{barcode.strip().replace(chr(34), "")}"',
        "fmt": "json",
        "limit": "3",
    }
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}

    _rate_limit()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        log.debug(f"MusicBrainz release search failed for barcode {barcode!r}: {e}")
        return None

    try:
        payload = response.json()
    except ValueError as e:
        log.debug(f"MusicBrainz release search returned invalid json: {e}")
        return None

    matches: list[ReleaseMatch] = []
    for raw in payload.get("releases", []) or []:
        release_group = raw.get("release-group") or {}
        credit = raw.get("artist-credit") or []
        first_artist = credit[0] if credit else {}
        match: ReleaseMatch = {
            "mbid": release_group.get("id") or raw.get("id") or "",
            "title": raw.get("title") or "",
            "artist": first_artist.get("name") or "",
        }
        score = raw.get("score")
        if score is not None:
            match["score"] = int(score)
        matches.append(match)
    return matches


def search_release_by_barcode(barcode: str) -> list[ReleaseMatch] | None:
    """Look up releases by barcode, caching the results.

    Returns the top matches or None when the lookup is not possible.
    """
    key = "barcode|" + barcode.strip().lower()
    cached = _cache.get(key)
    if cached is not None:
        created_at, matches = cached
        if time.monotonic() - created_at < CACHE_TTL_SECONDS:
            return matches
        del _cache[key]

    matches = _request_releases_by_barcode(barcode)
    if matches is not None:
        _cache[key] = (time.monotonic(), matches)
    return matches


def clear_cache() -> None:
    """Forget all cached artist lookups."""
    _cache.clear()


__all__ = ["ArtistMatch", "ReleaseMatch", "clear_cache", "search_artist", "search_release_by_barcode"]
