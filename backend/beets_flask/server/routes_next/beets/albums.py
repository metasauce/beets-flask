from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, BeforeValidator, Field, model_validator
from quart import Blueprint, request
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.importer.types import BeetsAlbum
from beets_flask.server.exceptions import InvalidUsageError, NotFoundError
from beets_flask.server.routes_next.beets._query import (
    PaginatedQuery,
    build_filter_query,
)

from ..jsonapi import (
    LinkObject,
    MetaObject,
    ResourceIdentifier,
    error_responses,
)
from . import g
from ._types import (
    AlbumAttributes,
    AlbumResource,
    AlbumSortField,
    BulkFilterQueryParams,
    BulkResult,
    Cursor,
    Direction,
    ItemResource,
    MultiAlbumDocument,
    SingleAlbumDocument,
    Sort,
)
from .items import to_item_resource

if TYPE_CHECKING:
    from collections.abc import Iterable

    from beets_flask.importer.types import BeetsItem

albums_bp = Blueprint("albums", __name__, url_prefix="/albums")


def to_album_resource(album: BeetsAlbum, items: Iterable[BeetsItem]) -> AlbumResource:
    attributes = AlbumAttributes(
        album=album.album,
        albumartist=album.albumartist,
        year=album.year,
        # TODO: Add more in controlled way
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


class GetQueryParams(BaseModel):
    include: Annotated[
        Literal["items"] | None,
        Field(
            description="The album's items are included in the ``included`` "
            "section of the response"
        ),
    ] = None


@albums_bp.route("/<int:album_id>", methods=["GET"])
@validate_querystring(GetQueryParams)
@validate_response(SingleAlbumDocument)
@error_responses(NotFoundError)
async def get_album(album_id: int, query_args: GetQueryParams) -> SingleAlbumDocument:
    """Get album.

    Retrieve a single album from the beets library by its id.
    """
    album: BeetsAlbum | None = g.lib.get_album(album_id)
    if not album:
        raise NotFoundError(f"Album with beets_id:{album_id!r} not found in beets db.")

    items = album.items()
    included = (
        [to_item_resource(item) for item in items]
        if query_args.include == "items"
        else []
    )

    return SingleAlbumDocument(
        data=to_album_resource(album, items),
        included=included,
        links=LinkObject(self=request.url),
    )


@albums_bp.route("/<int:album_id>", methods=["PATCH"])
@validate_querystring(GetQueryParams)
@validate_request(AlbumAttributes)
@validate_response(SingleAlbumDocument)
@error_responses(InvalidUsageError, NotFoundError)
async def patch_album(
    album_id: int, query_args: GetQueryParams, data: AlbumAttributes
) -> SingleAlbumDocument:
    """Patch album.

    Update the attributes of a single album. The change is written back to the beets
    library and to the metadata of the files (if applicable).

    Attributes that are not present in the body are left unchanged; an
    explicit ``null`` clears the field.
    """
    album: BeetsAlbum | None = g.lib.get_album(album_id)
    if not album:
        raise NotFoundError(f"Album with beets_id:{album_id!r} not found in beets db.")

    album.update(data.patch_data())
    album.try_sync(True, False)

    items = album.items()
    included = (
        [to_item_resource(item) for item in items]
        if query_args.include == "items"
        else []
    )

    return SingleAlbumDocument(
        data=to_album_resource(album, items),
        included=included,
        links=LinkObject(self=request.url),
    )


class DeleteQueryParams(BaseModel):
    delete_files: Annotated[
        bool,
        Field(
            description="Also delete the album's files from disk",
        ),
    ] = False


@albums_bp.route("/<int:album_id>", methods=["DELETE"])
@validate_querystring(DeleteQueryParams)
@validate_response(SingleAlbumDocument)
@error_responses(InvalidUsageError, NotFoundError)
async def delete_album(
    album_id: int, query_args: DeleteQueryParams
) -> SingleAlbumDocument:
    """Delete album.

    Delete a single album from the beets library, together with all of its items.
    Use ``delete_files=true`` to also remove their files from disk.
    """
    album: BeetsAlbum | None = g.lib.get_album(album_id)
    if not album:
        raise NotFoundError(f"Album with beets_id:{album_id!r} not found in beets db.")

    resource = to_album_resource(album, album.items())
    album.remove(delete=query_args.delete_files)

    return SingleAlbumDocument(
        data=resource, included=[], links=LinkObject(self=request.url)
    )


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(BulkFilterQueryParams):
    """Query params of the albums bulk endpoint.

    ``cursor`` is mutually exclusive with ``sort``/the filters; ``include``
    is orthogonal and carried over by ``links.next``.
    """

    cursor: Annotated[
        Cursor[Sort[AlbumSortField]] | None,
        Field(
            description=(
                "Pagination cursor from the ``links.next`` of a previous response. "
                "The cursor is self-contained: it encodes the sort and the filters "
                "of the original request, so the following pages only need the "
                "cursor (plus an optional ``limit``). Cannot be combined with "
                "``sort``, ``filter_query`` or ``filter_ids``."
            ),
        ),
        BeforeValidator(
            Cursor[Sort[AlbumSortField]].from_string, json_schema_input_type=str
        ),
    ] = None
    sort: Annotated[
        Sort[AlbumSortField] | None,
        Field(
            description=(
                "Sort the results by one of: "
                + ", ".join(f"``{name}``" for name in AlbumSortField.values())
                + ". Prefix ``-`` for descending (default ``-added``) or ``+`` "
                "for ascending."
            ),
        ),
        BeforeValidator(Sort[AlbumSortField].from_str, json_schema_input_type=str),
    ] = None
    limit: Annotated[
        int,
        Field(description="Page size min 1, max 1000.", ge=1, le=1000),
    ] = 100
    include: Annotated[
        Literal["items"] | None,
        Field(
            description=(
                "Each album's items are embedded in the ``included`` section "
                "of the response."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def _cursor_is_exclusive(self) -> BulkGetQueryParams:
        """Cursor tokens are self-contained; reject combined filter/sort args."""
        if self.cursor and self.model_fields_set & {
            "filter_query",
            "filter_ids",
            "sort",
        }:
            raise ValueError(
                "cursor cannot be combined with filter_query, filter_ids or sort"
            )
        return self

    def to_cursor(self) -> Cursor[Sort[AlbumSortField]]:
        """Derive the page's cursor from the query params.

        Follow-up pages carry a decoded, self-contained ``cursor``; for the
        first page the cursor is built from ``sort`` (default ``-added``)
        and the filters.
        """
        if self.cursor is not None:
            return self.cursor

        # Default: newest first (``-added``).
        sort = self.sort or Sort[AlbumSortField](
            field=AlbumSortField.ADDED, direction=Direction.DESC
        )
        return Cursor(
            sort=sort,
            filter_query=self.filter_query,
            filter_ids=self.filter_ids,
        )


@albums_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiAlbumDocument)
@error_responses(InvalidUsageError)
async def get_albums(query_args: BulkGetQueryParams) -> MultiAlbumDocument:
    """Get albums (bulk).

    Retrieve beets albums filtered by ``filter_query``/``filter_ids`` (first
    page) or by the self-contained ``cursor`` from ``links.next`` (following
    pages); cursor and filters are mutually exclusive. Pass ``include=items``
    to embed each album's items in the ``included`` section.

    E.g. the 50 most recently added albums by Tool:
    ``GET /api_v1/beets/albums/?filter_query=albumartist:Tool&limit=50``
    """
    cursor = query_args.to_cursor()
    limit = query_args.limit

    # Fetch limit + 1 rows to detect whether a next page exists.
    page = PaginatedQuery(cursor, table="albums")
    rows = list(g.lib.albums(page, page, limit=limit + 1))
    has_next = len(rows) > limit
    albums = rows[:limit]

    # Create pagination links. The "next" link is only present if there
    # are more albums to fetch.
    include_items = query_args.include is not None
    links = LinkObject(self=request.url)
    if has_next:
        last_album = albums[-1]
        last_value = getattr(last_album, cursor.sort.field.value, None)
        next_cursor = cursor.next(
            None if last_value is None else str(last_value), last_album.id
        )
        next_params: dict[str, str | int] = {
            "cursor": next_cursor.to_string(),
            "limit": limit,
        }
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
        included=included or None,
        links=links,
        meta=MetaObject(total=page.total(g.lib)),
    )


@albums_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkFilterQueryParams)
@validate_request(AlbumAttributes)
@validate_response(BulkResult)
@error_responses(InvalidUsageError)
async def patch_albums(
    query_args: BulkFilterQueryParams, data: AlbumAttributes
) -> BulkResult:
    """Patch albums (bulk).

    Update the attributes of all albums matching the given filters. The change is
    applied to the beets library and written to the files' metadata if applicable.
    Attributes that are not present in the body are left unchanged; an explicit ``null``
    clears the field.
    """

    update_data = data.patch_data()
    query = build_filter_query(
        query_args.filter_query, query_args.filter_ids, BeetsAlbum
    )

    # Update every matching album in a single transaction
    total = 0
    with g.lib.transaction():
        for album in g.lib.albums(query):
            album.update(update_data)
            album.try_sync(True, False)
            total += 1

    return BulkResult(meta=MetaObject(total=total))


class BulkDeleteQueryParams(BulkFilterQueryParams):
    delete_files: Annotated[
        bool,
        Field(
            description="Also delete the album's files on disk",
        ),
    ] = False


@albums_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
@validate_response(BulkResult)
@error_responses(InvalidUsageError)
async def delete_albums(query_args: BulkDeleteQueryParams) -> BulkResult:
    """Delete albums (bulk).

    Delete all albums matching the given filters, together with all of
    their items. Pass ``delete_files=true`` to also remove the items'
    files from disk.
    """

    query = build_filter_query(
        query_args.filter_query, query_args.filter_ids, BeetsAlbum
    )

    # Delete every matching album in a single transaction
    total = 0
    with g.lib.transaction():
        for album in g.lib.albums(query):
            album.remove(delete=query_args.delete_files)
            total += 1

    return BulkResult(meta=MetaObject(total=total))
