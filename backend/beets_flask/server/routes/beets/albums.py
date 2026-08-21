from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Annotated, Literal, TypedDict

from msgspec import Meta
from quart import Blueprint, g
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BeetsAlbum, BeetsItem
from beets_flask.server.exceptions import (
    InvalidUsageException,
    NotFoundException,
    NotImplementedException,
    error_responses,
)

from ._types import (
    AlbumAttributes,
    AlbumResource,
    ItemResource,
    MultiAlbumDocument,
    SingleAlbumDocument,
)

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
@error_responses(InvalidUsageException, NotFoundException)
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
        included: list[ItemResource] = [
            {
                "type": "item",
                "id": str(item.id),
                "attributes": {"title": item.title},
            }
            for item in items
        ]
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
        included: list[ItemResource] = [
            {
                "type": "item",
                "id": str(item.id),
                "attributes": {"title": item.title},
            }
            for item in items
        ]
    else:
        included = []

    return {
        "data": to_album_resource(album, items),
        "included": included,
    }


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(TypedDict, total=False):
    cursor: Annotated[str, Meta(description="Pagination cursor from the previous page")]
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the albums")
    ]
    filter_ids: Annotated[
        list[int], Meta(description="Only return albums with these ids")
    ]
    sort: Annotated[
        str,
        Meta(description='Sort order as comma separated list, e.g. "+year,-title"'),
    ]
    limit: Annotated[
        int, Meta(description="Page size, i.e. maximum number of albums to return")
    ]
    include: Annotated[
        Literal["items"],
        Meta(
            description="Each album's items are included in the ``included`` "
            "section of the response"
        ),
    ]


@albums_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiAlbumDocument)
@error_responses(InvalidUsageException, NotImplementedException)
async def get_albums(query_args: BulkGetQueryParams) -> MultiAlbumDocument:
    """Get albums (bulk)

    Retrieve beets albums matching the given filters, with pagination.

    Not implemented yet - currently returns 501.
    """
    raise NotImplementedException


class BulkPatchQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the albums")
    ]
    filter_ids: Annotated[
        list[int], Meta(description="Only update albums with these ids")
    ]
    sort: Annotated[
        str,
        Meta(description='Sort order as comma separated list, e.g. "+year,-title"'),
    ]
    limit: Annotated[
        int, Meta(description="Page size, i.e. maximum number of albums to update")
    ]
    include: Annotated[
        Literal["items"],
        Meta(
            description="Each album's items are included in the ``included`` "
            "section of the response"
        ),
    ]


@albums_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkPatchQueryParams)
@validate_request(AlbumAttributes)
@validate_response(MultiAlbumDocument)
@error_responses(InvalidUsageException, NotImplementedException)
async def patch_albums(
    query_args: BulkPatchQueryParams, data: AlbumAttributes
) -> MultiAlbumDocument:
    """Patch albums (bulk)

    Update the attributes of all albums matching the given filters.

    Not implemented yet - currently returns 501.
    """
    raise NotImplementedException


class BulkDeleteQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the albums")
    ]
    filter_ids: Annotated[
        list[int], Meta(description="Only delete albums with these ids")
    ]
    delete_files: Annotated[
        bool, Meta(description="Also delete the album's files from disk")
    ]


@albums_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
@error_responses(InvalidUsageException, NotImplementedException)
async def delete_albums(query_args: BulkDeleteQueryParams):
    """Delete albums (bulk)

    Delete all albums matching the given filters. Will delete related
    items if they are dangling and have no other album assigned.

    Not implemented yet - currently returns 501.
    """
    raise NotImplementedException
