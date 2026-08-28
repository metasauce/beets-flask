from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Annotated, Literal, TypedDict
from urllib.parse import urlencode

from pydantic import Field
from quart import Blueprint, g, request
from quart_schema import validate_request, validate_response

from beets_flask.importer.types import BeetsAlbum, BeetsItem
from beets_flask.server.exceptions import (
    InvalidUsageException,
    NotFoundException,
)
from beets_flask.server.utility import ensure_writable
from beets_flask.server.validation import validate_querystring

from ..jsonapi import LinkObject, MetaObject, ResourceIdentifier, error_responses
from ._cursor import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PaginatedQuery,
    build_cursor,
    build_filter_query,
)
from ._types import (
    AlbumAttributes,
    AlbumResource,
    AlbumSort,
    AlbumSortField,
    BulkFilterParams,
    BulkResult,
    ItemResource,
    MultiAlbumDocument,
    SingleAlbumDocument,
)
from .items import to_item_resource

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

albums_bp = Blueprint("albums", __name__, url_prefix="/albums")


# Attributes that cannot be set via PATCH: they are derived from the
# library state and ignored in PATCH bodies.
READ_ONLY_ALBUM_ATTRIBUTES = frozenset({"sources"})


def to_album_resource(album: BeetsAlbum, items: Iterable[BeetsItem]) -> AlbumResource:
    attributes = AlbumAttributes(
        title=album.album,
        albumartist=album.albumartist,
        year=album.year,
    )

    # TODO: allow for source plugin adapter specific extraction
    # if data_source == "musibrainz:"

    return AlbumResource(
        type="album",
        id=str(album.id),
        attributes=attributes,
        relationships=[
            ResourceIdentifier[Literal["item"]](type="item", id=str(item.id))
            for item in items
        ],
    )


# ---------------------------------- Single ---------------------------------- #


class GetQueryParams(TypedDict, total=False):
    include: Annotated[
        Literal["items"],
        Field(
            description="The album's items are included in the ``included`` "
            "section of the response"
        ),
    ]


@albums_bp.route("/<int:album_id>", methods=["GET"])
@validate_querystring(GetQueryParams)
@validate_response(SingleAlbumDocument)
@error_responses(NotFoundException)
async def get_album(album_id: int, query_args: GetQueryParams) -> SingleAlbumDocument:
    """Get album

    Retrieve a single album from the beets library by its id.
    """
    album: BeetsAlbum = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:{album_id!r} not found in beets db."
        )

    items = album.items()
    included = (
        [to_item_resource(item) for item in items]
        if query_args.get("include") == "items"
        else []
    )

    return SingleAlbumDocument(data=to_album_resource(album, items), included=included)


@albums_bp.route("/<int:album_id>", methods=["PATCH"])
@validate_querystring(GetQueryParams)
@validate_request(AlbumAttributes)
@validate_response(SingleAlbumDocument)
@error_responses(InvalidUsageException, NotFoundException)
async def patch_album(
    album_id: int, query_args: GetQueryParams, data: AlbumAttributes
) -> SingleAlbumDocument:
    """Patch album

    Update the attributes of a single album, e.g. its title. The change
    is written back to the beets library.
    """
    album: BeetsAlbum = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:{album_id!r} not found in beets db."
        )

    ensure_writable()

    # ``model_fields_set`` are the attributes present in the request body:
    # absent fields are left unchanged, an explicit ``null`` clears.
    # Translate API attribute names to beets album field names
    # (``title`` is the API name for the beets ``album`` field) and
    # ignore read-only attributes (e.g. ``sources``).
    update_data: dict[str, object] = {}
    for key in data.model_fields_set:
        if key in READ_ONLY_ALBUM_ATTRIBUTES:
            continue
        update_data["album" if key == "title" else key] = getattr(data, key)

    if update_data:
        # Write back to file
        album.update(update_data)
        album.try_sync(True, False)

    items = album.items()
    included = (
        [to_item_resource(item) for item in items]
        if query_args.get("include") == "items"
        else []
    )

    return SingleAlbumDocument(data=to_album_resource(album, items), included=included)


class DeleteQueryParams(TypedDict, total=False):
    delete_files: Annotated[
        bool,
        Field(
            description="Also delete the album's files from disk",
            json_schema_extra={"default": False},
        ),
    ]


@albums_bp.route("/<int:album_id>", methods=["DELETE"])
@validate_querystring(DeleteQueryParams)
@validate_response(SingleAlbumDocument)
@error_responses(InvalidUsageException, NotFoundException)
async def delete_album(
    album_id: int, query_args: DeleteQueryParams
) -> SingleAlbumDocument:
    """Delete album

    Delete a single album from the beets library, together with all of
    its items; pass ``delete_files=true`` to also remove their files
    from disk.
    """
    album: BeetsAlbum = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:{album_id!r} not found in beets db."
        )

    ensure_writable()

    resource = to_album_resource(album, album.items())
    album.remove(delete=query_args.get("delete_files", False))
    return SingleAlbumDocument(data=resource, included=[])


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(BulkFilterParams, total=False):
    cursor: Annotated[
        str,
        Field(
            description=(
                "Pagination cursor from the ``links.next`` of a previous "
                "response. The cursor is self-contained: it encodes the sort "
                "and the filters of the original request, so the following "
                "pages only need the cursor (plus an optional ``limit``). "
                "Cannot be combined with ``sort``, ``filter_query`` or "
                "``filter_ids``."
            )
        ),
    ]
    sort: Annotated[
        AlbumSort,
        Field(
            description=(
                'Sort by a field, optionally prefixed with "+" (ascending) or '
                '"-" (descending), e.g. "+year". Default: "-added".'
            ),
            examples=["+year"],
            json_schema_extra={"default": "-added"},
        ),
    ]
    limit: Annotated[
        int,
        Field(
            description=(
                "Page size, i.e. maximum number of albums to return. Defaults "
                "to 100; the minimum is 1, the maximum is 1000."
            ),
            json_schema_extra={"default": 100},
        ),
    ]
    include: Annotated[
        Literal["items"],
        Field(
            description=(
                "Each album's items are included in the ``included`` section "
                "of the response. The ``links.next`` URL keeps the parameter, "
                "so pagination continues to include them."
            )
        ),
    ]


@albums_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiAlbumDocument)
@error_responses(InvalidUsageException)
async def get_albums(query_args: BulkGetQueryParams) -> MultiAlbumDocument:
    """Get albums (bulk)

    Retrieve beets albums matching the given filters, with pagination.

    **Filters**

    - ``filter_query``: a beets query string, e.g. ``artist:Tool``
    - ``filter_ids``: repeatable, explicit album ids

    The filters are combined with AND; without any filter, all albums
    match.

    **Pagination**

    The result is sorted by ``sort`` (default ``-added``) and paginated
    with a keyset cursor. Request the first page with ``sort`` and the
    filters; the ``links.next`` of the response carries a self-contained
    cursor that encodes the sort and the filters, so the following pages
    only need that cursor (plus an optional ``limit``). The cursor cannot
    be combined with ``sort`` or the filters.

    ``meta.total`` is the total number of matching albums, independent
    of the page size.

    **Items**

    Pass ``include=items`` to embed each album's items in the
    ``included`` section of the response. The parameter is carried over
    by the ``links.next`` URL, so pagination keeps including them.

    For example, the 50 most recently added albums by Tool:
    ``GET /api_v1/beets/albums/?filter_query=albumartist:Tool&limit=50``
    """
    # Construct cursor either from args or from the encoded cursor string.
    cursor = build_cursor(query_args, AlbumSortField.values())

    # Limit is independent from cursor
    limit = query_args.get("limit", DEFAULT_LIMIT)
    if limit < 1:
        raise InvalidUsageException("limit must be positive")
    if limit > MAX_LIMIT:
        raise InvalidUsageException(f"limit must not exceed {MAX_LIMIT}")

    query = PaginatedQuery(cursor, limit + 1, "albums")
    rows = list(g.lib.albums(query, query))
    has_next = len(rows) > limit
    albums = rows[:limit]

    # Create pagination links. The "next" link is only present if there
    # are more albums to fetch.
    include_items = query_args.get("include") == "items"
    links = LinkObject(self=request.url)
    if has_next:
        cursor_token = cursor.next_from_entity(albums[-1]).to_string()
        next_params: dict[str, str | int] = {"cursor": cursor_token, "limit": limit}
        if include_items:
            next_params["include"] = "items"
        links.next = request.base_url + "?" + urlencode(next_params)

    data: list[AlbumResource] = []
    included: list[ItemResource] = []
    for album in albums:
        items = album.items()
        data.append(to_album_resource(album, items))
        if include_items:
            included.extend(to_item_resource(item) for item in items)

    return MultiAlbumDocument(
        data=data,
        included=included,
        links=links,
        meta=MetaObject(total=query.total(g.lib)),
    )


class BulkPatchQueryParams(BulkFilterParams, total=False):
    """Query parameters of the bulk PATCH endpoint."""


@albums_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkPatchQueryParams)
@validate_request(AlbumAttributes)
@validate_response(BulkResult)
@error_responses(InvalidUsageException)
async def patch_albums(
    query_args: BulkPatchQueryParams, data: AlbumAttributes
) -> BulkResult:
    """Patch albums (bulk)

    Update the attributes of all albums matching the given filters. The
    change is applied to the beets library and written to the tags of
    the albums' items, like the single album patch. Attributes that
    are not present in the body are left unchanged.

    The ``filter_query`` and ``filter_ids`` parameters are combined
    with AND; without any filter, all albums match. All updates run in
    a single transaction and are committed together.

    Returns 400 if the library is configured as read-only or the body
    does not contain any attributes.
    """
    ensure_writable()

    # ``model_fields_set`` are the attributes present in the request body:
    # absent fields are left unchanged, an explicit ``null`` clears.
    # Translate API attribute names to beets album field names
    # (``title`` is the API name for the beets ``album`` field) and
    # ignore read-only attributes (e.g. ``sources``).
    update_data: dict[str, object] = {}
    for key in data.model_fields_set:
        if key in READ_ONLY_ALBUM_ATTRIBUTES:
            continue
        update_data["album" if key == "title" else key] = getattr(data, key)

    query = build_filter_query(
        query_args.get("filter_query"), query_args.get("filter_ids"), BeetsAlbum
    )

    if not update_data:
        raise InvalidUsageException("No attributes to update")

    # Update every matching album in a single transaction: the database
    # writes are committed together. If an update fails midway, the
    # already-written files stay consistent with the committed database
    # state, and the error propagates.
    total = 0
    with g.lib.transaction():
        for album in g.lib.albums(query):
            album.update(update_data)
            album.try_sync(True, False)
            total += 1

    return BulkResult(meta=MetaObject(total=total))


class BulkDeleteQueryParams(BulkFilterParams, total=False):
    delete_files: Annotated[
        bool,
        Field(
            description="Also delete the album's files from disk",
            json_schema_extra={"default": False},
        ),
    ]


@albums_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
@validate_response(BulkResult)
@error_responses(InvalidUsageException)
async def delete_albums(query_args: BulkDeleteQueryParams) -> BulkResult:
    """Delete albums (bulk)

    Delete all albums matching the given filters, together with all of
    their items; pass ``delete_files=true`` to also remove the items'
    files from disk.

    The ``filter_query`` and ``filter_ids`` parameters are combined
    with AND; without any filter, all albums match. All deletions run
    in a single transaction and are committed together.

    Returns 400 if the library is configured as read-only.
    """
    ensure_writable()

    query = build_filter_query(
        query_args.get("filter_query"), query_args.get("filter_ids"), BeetsAlbum
    )

    # Delete every matching album in a single transaction: the database
    # writes are committed together. If a deletion fails midway, the
    # already-deleted files stay consistent with the committed database
    # state, and the error propagates.
    delete = query_args.get("delete_files", False)
    total = 0
    with g.lib.transaction():
        for album in g.lib.albums(query):
            album.remove(delete=delete)
            total += 1

    return BulkResult(meta=MetaObject(total=total))
