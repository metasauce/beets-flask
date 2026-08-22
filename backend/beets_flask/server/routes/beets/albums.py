from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Annotated, Literal, TypeAlias, TypedDict
from urllib.parse import urlencode

from beets.dbcore.query import AndQuery, InQuery, Query
from msgspec import Meta
from quart import Blueprint, g, request
from quart_schema import validate_request, validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BeetsAlbum, BeetsItem
from beets_flask.server.exceptions import (
    InvalidUsageException,
    NotFoundException,
    error_responses,
)

from ._cursor import Cursor, PaginatedQuery, parse_filter_query
from ._types import (
    AlbumAttributes,
    AlbumResource,
    BulkResult,
    ItemResource,
    LinkObject,
    MultiAlbumDocument,
    SingleAlbumDocument,
)
from ._validation import validate_querystring
from .items import DEFAULT_LIMIT, MAX_LIMIT, to_item_resource

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

albums_bp = Blueprint("albums", __name__, url_prefix="/albums")


def to_album_resource(album: BeetsAlbum, items: Iterable[BeetsItem]) -> AlbumResource:
    return {
        "type": "album",
        "id": str(album.id),
        "attributes": {"title": album.album},
        "relationships": [
            {
                "type": "item",
                "id": str(item.id),
            }
            for item in items
        ],
    }


#: The bare sortable field names of the bulk endpoints.
ALBUM_SORTABLE_FIELDS = (
    "added",
    "year",
    "album",
    "albumartist",
    "disctotal",
)

#: All allowed ``sort`` values: a sortable field, optionally prefixed
#: with "+" (ascending) or "-" (descending). The prefixes are generated
#: programmatically from :data:`ALBUM_SORTABLE_FIELDS`.
AlbumSortableField: TypeAlias = Literal[  # type: ignore[valid-type]
    *(
        entry
        for field in ALBUM_SORTABLE_FIELDS
        for entry in (field, f"+{field}", f"-{field}")
    )
]  # mypy does not support PEP 646 star-unpacking in Literal yet

#: Description of the ``sort`` query parameter of the bulk endpoints.
#: Computed at module level (not inside an annotation) because f-strings
#: inside ``Annotated`` are not constant-folded and break under
#: ``from __future__ import annotations``.
ALBUM_SORT_PARAM_DESCRIPTION = (
    'Sort by a field, optionally prefixed with "+" (ascending) or "-" '
    '(descending), e.g. "+year". Allowed fields: '
    f'{", ".join(ALBUM_SORTABLE_FIELDS)}. Default: "-added".'
)


# ---------------------------------- Single ---------------------------------- #


class GetQueryParams(TypedDict, total=False):
    include: Annotated[
        Literal["items"],
        Meta(
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
    if query_args.get("include") == "items":
        included: list[ItemResource] = [to_item_resource(item) for item in items]
    else:
        included = []

    return {
        "data": to_album_resource(album, items),
        "included": included,
    }


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

    if get_config().data.gui.library.readonly:
        raise InvalidUsageException("Library is read-only")

    # Translate API attribute names to beets album field names.
    update_data: dict[str, str] = {}
    if "title" in data:
        update_data["album"] = data["title"]

    if update_data:
        # Write back to file
        album.update(update_data)
        album.try_sync(True, False)

    items = album.items()
    if query_args.get("include") == "items":
        included: list[ItemResource] = [to_item_resource(item) for item in items]
    else:
        included = []

    return {
        "data": to_album_resource(album, items),
        "included": included,
    }


class DeleteQueryParams(TypedDict, total=False):
    delete_files: Annotated[
        bool,
        Meta(
            description="Also delete the album's files from disk",
            extra_json_schema={"default": False},
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

    if get_config().data.gui.library.readonly:
        raise InvalidUsageException("Library is read-only")

    resource = to_album_resource(album, album.items())
    album.remove(delete=query_args.get("delete_files", False))
    return {
        "data": resource,
        "included": [],
    }


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(TypedDict, total=False):
    cursor: Annotated[
        str,
        Meta(
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
    filter_query: Annotated[
        str,
        Meta(
            description=(
                "Beets query string to filter the albums, e.g. ``artist:Tool``. "
                "Combined with ``filter_ids`` using AND."
            ),
            examples=["artist:Tool"],
        ),
    ]
    filter_ids: Annotated[
        list[int],
        Meta(
            description=(
                "Only return albums with these ids. Repeat the parameter for "
                "multiple ids, e.g. ``filter_ids=1&filter_ids=2``. Combined "
                "with ``filter_query`` using AND."
            )
        ),
    ]
    sort: Annotated[
        AlbumSortableField,
        Meta(
            description=ALBUM_SORT_PARAM_DESCRIPTION,
            examples=["+year"],
            extra_json_schema={"default": "-added"},
        ),
    ]
    limit: Annotated[
        int,
        Meta(
            description=(
                "Page size, i.e. maximum number of albums to return. Defaults "
                "to 100; the minimum is 1, the maximum is 1000."
            ),
            extra_json_schema={"default": 100},
        ),
    ]
    include: Annotated[
        Literal["items"],
        Meta(
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
    # The cursor is self-contained
    if "cursor" in query_args and any(
        query_args.get(p) for p in ("sort", "filter_query", "filter_ids")
    ):
        raise InvalidUsageException("cursor cannot be combined with sort or filters")

    try:
        if cursor_token := query_args.get("cursor"):
            # Re-validate the sort: the token is client-supplied and
            # bypasses the sort enum above.
            cursor = Cursor.from_string(cursor_token)
            cursor.validate_sort_allowed(ALBUM_SORTABLE_FIELDS)
        else:
            cursor = Cursor.initial(
                query_args.get("sort"),
                filter_query=query_args.get("filter_query"),
                # The cursor stores ids as strings; see Cursor.from_string.
                filter_ids=(
                    [str(i) for i in query_args["filter_ids"]]
                    if query_args.get("filter_ids") is not None
                    else None
                ),
            )
    except ValueError as exc:
        raise InvalidUsageException(str(exc)) from exc

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
    links: LinkObject = {"self": request.url}
    if has_next:
        cursor_token = cursor.next_from_entity(albums[-1]).to_string()
        next_params: dict[str, str | int] = {"cursor": cursor_token, "limit": limit}
        if include_items:
            next_params["include"] = "items"
        links["next"] = request.base_url + "?" + urlencode(next_params)

    data: list[AlbumResource] = []
    included: list[ItemResource] = []
    for album in albums:
        items = album.items()
        data.append(to_album_resource(album, items))
        if include_items:
            included.extend(to_item_resource(item) for item in items)

    return {
        "data": data,
        "included": included,
        "links": links,
        "meta": {"total": query.total(g.lib)},
    }


class BulkPatchQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str,
        Meta(
            description=(
                "Beets query string to filter the albums, e.g. ``artist:Tool``. "
                "Combined with ``filter_ids`` using AND."
            ),
            examples=["artist:Tool"],
        ),
    ]
    filter_ids: Annotated[
        list[int],
        Meta(
            description=(
                "Only update albums with these ids. Repeat the parameter for "
                "multiple ids, e.g. ``filter_ids=1&filter_ids=2``. Combined "
                "with ``filter_query`` using AND."
            )
        ),
    ]


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

    Returns 400 if the library is configured as read-only.
    """
    if get_config().data.gui.library.readonly:
        raise InvalidUsageException("Library is read-only")

    # Translate API attribute names to beets album field names.
    update_data: dict[str, str] = {}
    if "title" in data:
        update_data["album"] = data["title"]

    # The filters: the beets query string and/or explicit ids
    filters: list[Query] = []
    if filter_query := query_args.get("filter_query"):
        filters.append(parse_query_string(filter_query, BeetsAlbum)[0])
    if filter_ids := query_args.get("filter_ids"):
        filters.append(InQuery("id", filter_ids))
    query = AndQuery(filters) if filters else None

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

    return {"meta": {"total": total}}


class BulkDeleteQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str,
        Meta(
            description=(
                "Beets query string to filter the albums, e.g. ``artist:Tool``. "
                "Combined with ``filter_ids`` using AND."
            ),
            examples=["artist:Tool"],
        ),
    ]
    filter_ids: Annotated[
        list[int],
        Meta(
            description=(
                "Only delete albums with these ids. Repeat the parameter for "
                "multiple ids, e.g. ``filter_ids=1&filter_ids=2``. Combined "
                "with ``filter_query`` using AND."
            )
        ),
    ]
    delete_files: Annotated[
        bool,
        Meta(
            description="Also delete the album's files from disk",
            extra_json_schema={"default": False},
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
    if get_config().data.gui.library.readonly:
        raise InvalidUsageException("Library is read-only")

    # The filters: the beets query string and/or explicit ids
    filters: list[Query] = []
    if filter_query := query_args.get("filter_query"):
        filters.append(parse_query_string(filter_query, BeetsAlbum)[0])
    if filter_ids := query_args.get("filter_ids"):
        filters.append(InQuery("id", filter_ids))
    query = AndQuery(filters) if filters else None

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

    return {"meta": {"total": total}}
