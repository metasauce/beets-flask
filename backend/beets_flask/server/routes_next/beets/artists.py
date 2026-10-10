from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

import numpy as np
from cachetools import TTLCache, cached
from pydantic import BaseModel, BeforeValidator, Field, model_validator
from quart import Blueprint, request
from quart_schema import validate_querystring, validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BEETS_DB_MULTI_VALUE_DELIMITER
from beets_flask.server.exceptions import InvalidUsageError, NotFoundError
from beets_flask.server.routes_next.beets._query import PaginatedArtists

from ..jsonapi import LinkObject, MetaObject, error_responses
from . import g
from ._types import (
    ArtistAttributes,
    ArtistResource,
    ArtistSortField,
    Cursor,
    Direction,
    MultiArtistDocument,
    SingleArtistDocument,
    Sort,
)

artists_bp = Blueprint("artists", __name__, url_prefix="/artists")


def artist_separators() -> list[str]:
    """The configured separators that split artist strings into artists."""
    return get_config().data.gui.library.artist_separators


def _split_multivalue(value: str, separators: list[str]) -> list[str]:
    """Split a string into multiple values using a list of separators.

    Beets stores multiple values in MultiValueFields using the DB_MULTI_VALUE_DELIMITER.
    Sadly artist and albumartist are not migrated to this standard yet (as beets 2.14).
    """

    # I benchmarked this, a single str.replace is more performant than using regex
    # here! Or even numpy char vectorization. This holds for len(seperators) < 5
    for separator in separators:
        value = value.replace(separator, BEETS_DB_MULTI_VALUE_DELIMITER)

    return [
        name.strip()
        for name in value.split(BEETS_DB_MULTI_VALUE_DELIMITER)
        if name.strip()
    ]


def _to_datetime(added: float) -> datetime | None:
    """Convert beets' unix-seconds ``added`` value to a datetime."""
    return datetime.fromtimestamp(added, tz=UTC) if math.isfinite(added) else None


def _aggregate(
    artist: str | None, separators: list[str]
) -> dict[str, ArtistAttributes]:
    """Aggregate the artists of the library (the uncached core of :func:`artists`)."""
    ids: dict[str, int] = {}
    row_ids: list[int] = []
    row_kinds: list[int] = []
    row_added: list[float] = []

    with g.lib.transaction() as tx:
        rows = tx.query(
            # 0 = item, 1 = album; the artist filter is optional
            """
            SELECT kind, artist, artists, added
            FROM (
                SELECT 0 AS kind, artist, artists, added
                FROM items
                UNION ALL
                SELECT 1 AS kind, albumartist AS artist,
                       albumartists AS artists, added
                FROM albums
            )
            WHERE ? IS NULL OR instr(artist, ?) > 0 OR instr(artists, ?) > 0
        """,
            (artist, artist, artist),
        )

    for row in rows:
        added = row["added"] or np.nan

        # Prefer to use the multi-value field, but fall back to the scalar field if
        # empty.
        value = row["artists"] or row["artist"] or ""

        for name in _split_multivalue(value, separators):
            index = ids.setdefault(name, len(ids))
            row_ids.append(index)
            row_kinds.append(row["kind"])
            row_added.append(added)

    count = len(ids)
    ids_array = np.asarray(row_ids, dtype=np.int64)
    kinds_array = np.asarray(row_kinds, dtype=np.bool_)
    added_array = np.asarray(row_added, dtype=np.float64)

    # Shape: (artist, kind), where kind 0 = item, 1 = album.
    shape = (count, 2)
    flat_ids = ids_array * 2 + kinds_array

    counts = np.bincount(flat_ids, minlength=count * 2).reshape(shape)
    first = np.full(count * 2, np.inf)
    last = np.full(count * 2, -np.inf)

    # Reduce all rows belonging to the same (artist, kind) group.
    np.fmin.at(first, flat_ids, added_array)
    np.fmax.at(last, flat_ids, added_array)

    # .tolist() avoids boxing a numpy scalar per artist in the loop below.
    counts = counts.tolist()
    first = first.reshape(shape).tolist()
    last = last.reshape(shape).tolist()

    return {
        name: ArtistAttributes(
            artist=name,
            item_count=counts[index][0],
            album_count=counts[index][1],
            first_item_added=_to_datetime(first[index][0]),
            last_item_added=_to_datetime(last[index][0]),
            first_album_added=_to_datetime(first[index][1]),
            last_album_added=_to_datetime(last[index][1]),
        )
        for name, index in ids.items()
    }


def _artists_cache_key() -> tuple[object, ...]:
    """Cache key of the full aggregation: library state + separators."""
    try:
        stat = g.lib.path.stat()
    except OSError:
        stat = None
    return (
        str(g.lib.path),
        stat.st_mtime_ns if stat else None,
        stat.st_size if stat else None,
        tuple(artist_separators()),
    )


@cached(cache=TTLCache(maxsize=8, ttl=60), key=_artists_cache_key, info=True)
def _all_artists() -> dict[str, ArtistAttributes]:
    """The cached library-wide aggregation (see :func:`artists`)."""
    return _aggregate(None, artist_separators())


def artists(artist: str | None = None) -> dict[str, ArtistAttributes]:
    """All artists of the library with aggregated item/album counts.

    Artists are not a beets entity: the multi-value ``artists`` and
    ``albumartists`` fields are split on beets' built-in delimiter, falling
    back to the scalar ``artist``/``albumartist`` fields and the configured
    separators. The matching items and albums are aggregated per artist.

    The library-wide list is cached per library state and separators, so the
    following pages of a paginated request do not re-aggregate it. A single
    artist is queried directly instead, so a cold lookup stays cheap.

    Pass ``artist`` to only aggregate the rows of that artist.
    """
    if artist is not None:
        return _aggregate(artist, artist_separators())
    return _all_artists()


def to_artist_resource(attributes: ArtistAttributes) -> ArtistResource:
    """Wrap aggregated artist attributes into a resource."""
    return ArtistResource(type="artist", id=attributes.artist, attributes=attributes)


# ---------------------------------- Single ---------------------------------- #


@artists_bp.route("/<path:artist_name>", methods=["GET"])
@validate_response(SingleArtistDocument)
@error_responses(NotFoundError)
async def get_artist(artist_name: str) -> SingleArtistDocument:
    """Get artist.

    Retrieve a single artist by name. Artists are not a beets entity, but
    are derived from the items and albums of the library: an artist is
    identified by its (split) name.
    """
    attributes = artists(artist_name).get(artist_name)
    if attributes is None:
        raise NotFoundError(f"Artist {artist_name!r} not found in beets db.")

    return SingleArtistDocument(
        data=to_artist_resource(attributes), links=LinkObject(self=request.url)
    )


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(BaseModel):
    """Query params of the artists bulk endpoint.

    ``cursor`` is mutually exclusive with ``sort``; follow-up pages only
    need the self-contained cursor (plus an optional ``limit``).
    """

    cursor: Annotated[
        Cursor[Sort[ArtistSortField]] | None,
        Field(
            description=(
                "Pagination cursor from the ``links.next`` of a previous "
                "response. The cursor is self-contained: it encodes the sort "
                "of the original request, so the following pages only need "
                "the cursor (plus an optional ``limit``). Cannot be combined "
                "with ``sort``."
            ),
        ),
        BeforeValidator(
            Cursor[Sort[ArtistSortField]].from_string, json_schema_input_type=str
        ),
    ] = None
    sort: Annotated[
        Sort[ArtistSortField] | None,
        Field(
            description=(
                "Sort the results by one of: "
                + ", ".join(f"``{name}``" for name in ArtistSortField.values())
                + ". Prefix ``-`` for descending or ``+`` for ascending "
                "(default ``artist``)."
            ),
        ),
        BeforeValidator(Sort[ArtistSortField].from_str, json_schema_input_type=str),
    ] = None
    limit: Annotated[
        int,
        Field(description="Page size min 1, max 1000.", ge=1, le=1000),
    ] = 100

    @model_validator(mode="after")
    def _cursor_is_exclusive(self) -> BulkGetQueryParams:
        """Cursor tokens are self-contained; reject a combined sort arg."""
        if self.cursor and "sort" in self.model_fields_set:
            raise ValueError("cursor cannot be combined with sort")
        return self

    def to_cursor(self) -> Cursor[Sort[ArtistSortField]]:
        """Derive the page's cursor from the query params.

        Follow-up pages carry a decoded, self-contained ``cursor``; for the
        first page the cursor is built from ``sort`` (default ``artist``).
        """
        if self.cursor is not None:
            return self.cursor

        sort = self.sort or Sort[ArtistSortField](
            field=ArtistSortField.ARTIST, direction=Direction.ASC
        )
        return Cursor(sort=sort)


@artists_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiArtistDocument)
@error_responses(InvalidUsageError)
async def get_artists(query_args: BulkGetQueryParams) -> MultiArtistDocument:
    """Get artists (bulk).

    Retrieve all artists of the beets library, sorted and paginated. Use
    the self-contained ``cursor`` from ``links.next`` for the following
    pages; cursor and sort are mutually exclusive.

    E.g. the 50 artists with the most items:
    ``GET /api_v1/beets/artists/?sort=-item_count&limit=50``
    """
    cursor = query_args.to_cursor()
    limit = query_args.limit

    page = PaginatedArtists(cursor, list(artists().values()))
    rows = page.fetch(limit + 1)

    links = LinkObject(self=request.url)
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = cursor.next(
            str(getattr(last, cursor.sort.field.value)), last.artist
        )
        links.next = (
            request.base_url
            + "?"
            + urlencode({"cursor": next_cursor.to_string(), "limit": limit})
        )

    return MultiArtistDocument(
        data=[to_artist_resource(row) for row in rows[:limit]],
        links=links,
        meta=MetaObject(total=page.total()),
    )
