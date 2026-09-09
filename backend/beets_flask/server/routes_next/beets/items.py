from __future__ import annotations

from typing import TYPE_CHECKING

from quart import Blueprint
from quart_schema import validate_response

from beets_flask.server.exceptions import (
    NotFoundError,
)

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
