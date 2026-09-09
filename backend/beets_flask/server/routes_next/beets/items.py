from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, Field
from quart import Blueprint
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.server.exceptions import InvalidUsageError, NotFoundError

from ..jsonapi import error_responses
from . import g
from ._types import (
    ItemAttributes,
    ItemResource,
    SingleItemDocument,
)

if TYPE_CHECKING:
    from beets_flask.importer.types import BeetsItem

items_bp = Blueprint("items", __name__, url_prefix="/items")


def to_item_resource(item: BeetsItem) -> ItemResource:
    attributes = ItemAttributes(
        title=item.title,
        artist=item.artist,
        # TODO: Add more in controlled way
    )

    # TODO: allow for source plugin adapter specific extraction
    # e.g. if data_source == "musibrainz:"

    return ItemResource(
        type="item",
        id=str(item.id),
        attributes=attributes,
    )


# ---------------------------------- Single ---------------------------------- #


@items_bp.route("/<int:item_id>", methods=["GET"])
@validate_response(SingleItemDocument)
@error_responses(NotFoundError)
async def get_item(item_id: int) -> SingleItemDocument:
    """Get item.

    Retrieve a single item from the beets library by its id.
    """
    item: BeetsItem | None = g.lib.get_item(item_id)
    if not item:
        raise NotFoundError(f"Item with beets_id:{item_id!r} not found in beets db.")

    return SingleItemDocument(data=to_item_resource(item))


@items_bp.route("/<int:item_id>", methods=["PATCH"])
@validate_request(ItemAttributes)
@validate_response(SingleItemDocument)
@error_responses(InvalidUsageError, NotFoundError)
async def patch_item(item_id: int, data: ItemAttributes) -> SingleItemDocument:
    """Patch item.

    Update the attributes of a single item. The change is written back to the beets
    library and to the metadata of the file (if applicable).

    Attributes that are not present in the body are left unchanged; an
    explicit ``null`` clears the field.
    """
    item: BeetsItem | None = g.lib.get_item(item_id)
    if not item:
        raise NotFoundError(f"Item with beets_id:{item_id!r} not found in beets db.")

    item.update(data.patch_data())
    item.try_sync(True, False)

    return SingleItemDocument(data=to_item_resource(item))


class DeleteQueryParams(BaseModel):
    delete_file: Annotated[
        bool,
        Field(
            description="Also delete the item's file from disk",
        ),
    ] = False


@items_bp.route("/<int:item_id>", methods=["DELETE"])
@validate_querystring(DeleteQueryParams)
@validate_response(SingleItemDocument)
@error_responses(InvalidUsageError, NotFoundError)
async def delete_item(
    item_id: int, query_args: DeleteQueryParams
) -> SingleItemDocument:
    """Delete item.

    Delete a single item from the beets library. Use ``delete_file=true`` to also remove
    its file from disk. If the item was the last one of its album, the
    album is removed as well.
    """
    item: BeetsItem | None = g.lib.get_item(item_id)
    if not item:
        raise NotFoundError(f"Item with beets_id:{item_id!r} not found in beets db.")

    resource = to_item_resource(item)
    item.remove(delete=query_args.delete_file, with_album=True)

    return SingleItemDocument(data=resource)
