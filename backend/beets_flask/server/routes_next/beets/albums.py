from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field
from quart import Blueprint
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.server.exceptions import InvalidUsageError, NotFoundError

from ..jsonapi import ResourceIdentifier, error_responses
from . import g
from ._types import (
    AlbumAttributes,
    AlbumResource,
    SingleAlbumDocument,
)
from .items import to_item_resource

if TYPE_CHECKING:
    from collections.abc import Iterable

    from beets_flask.importer.types import BeetsAlbum, BeetsItem

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

    return SingleAlbumDocument(data=to_album_resource(album, items), included=included)


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

    return SingleAlbumDocument(data=to_album_resource(album, items), included=included)


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

    return SingleAlbumDocument(data=resource, included=[])
