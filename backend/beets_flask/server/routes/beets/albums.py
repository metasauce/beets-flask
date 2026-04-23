from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

from quart import Blueprint, g
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.server.exceptions import NotFoundException

from ._types import (
    AlbumAttributes,
    MultiAlbumDocument,
    SingleAlbumDocument,
)

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

albums_bp = Blueprint("albums", __name__, url_prefix="/albums")

# ---------------------------------- Single ---------------------------------- #


@albums_bp.route("/<int:album_id>", methods=["GET"])
@validate_response(SingleAlbumDocument)
async def get_album(album_id: int) -> SingleAlbumDocument:
    """GET album - Retrieve a single beets album by ID"""

    album = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(f"Album with beets_id:{id!r} not found in beets db.")
    document: SingleAlbumDocument = {
        "data": {
            "id": str(album.id),
            "type": "album",
            "attributes": {"title": album.album},
            "relationships": [],
        },
        "included": [],  # TODO add items
    }
    return document


@albums_bp.route("/<int:album_id>", methods=["PATCH"])
@validate_request(AlbumAttributes)
@validate_response(SingleAlbumDocument)
async def patch_album(album_id: str, data: AlbumAttributes) -> SingleAlbumDocument:
    """PATCH album - Update a single beets album by ID"""
    raise NotImplemented


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
async def get_items(query_args: BulkGetQueryParams) -> MultiAlbumDocument:
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
async def patch_items(
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
async def delete_items(query_args: BulkDeleteQueryParams):
    """DELETE albums - Delete beets albums

    Will delete related items if the are dangling and have no
    other album assigned.
    """
    raise NotImplemented
