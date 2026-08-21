from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal, TypedDict

from quart import Blueprint, g
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BeetsAlbum, BeetsItem
from beets_flask.server.exceptions import NotFoundException

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
    include: Literal["items"]
    # whether to include related items in the response


@albums_bp.route("/<int:album_id>", methods=["GET"])
@validate_querystring(GetQueryParams)
@validate_response(SingleAlbumDocument)
async def get_album(album_id: int, query_args: GetQueryParams) -> SingleAlbumDocument:
    """GET album - Retrieve a single beets album by ID"""
    album = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(f"Album with beets_id:{id!r} not found in beets db.")

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
async def patch_album(
    album_id: int, query_args: GetQueryParams, data: AlbumAttributes
) -> SingleAlbumDocument:
    """PATCH album - Update a single beets album by ID"""
    album = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:{album_id!r} not found in beets db."
        )

    if get_config().data.gui.library.readonly:
        raise ValueError("Library is read-only")

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
    cursor: str  # pagination cursor
    filter_query: str
    filter_ids: list[int]
    sort: str  # "+year,-title"
    limit: int  # page size
    include: Literal["items"]


@albums_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiAlbumDocument)
async def get_albums(query_args: BulkGetQueryParams) -> MultiAlbumDocument:
    """GET albums - Retrieve beets albums

    Lets you retrieve beets albums.
    """
    raise NotImplemented


class BulkPatchQueryParams(TypedDict, total=False):
    filter_query: str
    filter_ids: list[int]
    sort: str  # "+year,-title"
    limit: int  # page size
    include: Literal["items"]


@albums_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkPatchQueryParams)
@validate_request(AlbumAttributes)
@validate_response(MultiAlbumDocument)
async def patch_albums(
    query_args: BulkPatchQueryParams, data: AlbumAttributes
) -> MultiAlbumDocument:
    """PATCH albums - Update beets albums

    Lets you update beets albums.
    """
    raise NotImplemented


class BulkDeleteQueryParams(TypedDict, total=False):
    filter_query: str
    filter_ids: list[int]
    delete_files: bool


@albums_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
async def delete_albums(query_args: BulkDeleteQueryParams):
    """DELETE albums - Delete beets albums

    Will delete related items if the are dangling and have no
    other album assigned.
    """
    raise NotImplemented
