from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, TypedDict

from msgspec import Meta
from quart import Blueprint, g
from quart_schema import validate_querystring, validate_request
from quart_schema.validation import validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BeetsItem
from beets_flask.server.exceptions import NotImplementedException, error_responses
from beets_flask.server.routes.exception import InvalidUsageException, NotFoundException

from ._types import (
    ItemAttributes,
    ItemResource,
    MultiItemDocument,
    SingleItemDocument,
)

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

items_bp = Blueprint("items", __name__, url_prefix="/items")


def to_item_resource(item: BeetsItem) -> ItemResource:
    return {
        "type": "item",
        "id": str(item.id),
        "attributes": {"title": item.title},
    }


# ---------------------------------- Single ---------------------------------- #


@items_bp.route("/<int:item_id>", methods=["GET"])
@validate_response(SingleItemDocument)
@error_responses(NotFoundException)
async def get_item(item_id: int) -> SingleItemDocument:
    """Get item

    Retrieve a single item from the beets library by its id.
    """
    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:{item_id!r} not found in beets db."
        )

    return {
        "data": to_item_resource(item),
    }


@items_bp.route("/<int:item_id>", methods=["PATCH"])
@validate_request(ItemAttributes)
@validate_response(SingleItemDocument)
@error_responses(InvalidUsageException, NotFoundException)
async def patch_item(item_id: int, data: ItemAttributes) -> SingleItemDocument:
    """Patch item

    Update the attributes of a single item, e.g. its title. The change
    is written back to the beets library and to disk (if applicable).
    """
    item: BeetsItem = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:{item_id!r} not found in beets db."
        )

    if get_config().data.gui.library.readonly:
        raise InvalidUsageException("Library is read-only")

    update_data: ItemAttributes = {}
    if "title" in data:
        update_data["title"] = data["title"]

    if update_data:
        item.update(update_data)
        item.try_sync(True, False)

    return {
        "data": to_item_resource(item),
    }


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(TypedDict, total=False):
    cursor: Annotated[str, Meta(description="Pagination cursor from the previous page")]
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the items")
    ]
    filter_ids: Annotated[
        list[str], Meta(description="Only return items with these ids")
    ]
    sort: Annotated[
        str,
        Meta(description='Sort order as comma separated list, e.g. "+year,-title"'),
    ]
    limit: Annotated[
        int, Meta(description="Page size, i.e. maximum number of items to return")
    ]


@items_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiItemDocument)
@error_responses(InvalidUsageException, NotImplementedException)
async def get_items(query_args: BulkGetQueryParams) -> MultiItemDocument:
    """Get items (bulk)

    Retrieve beets items matching the given filters, with pagination.

    Not implemented yet - currently returns 501.
    """
    raise NotImplementedException


class BulkPatchQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the items")
    ]
    filter_ids: Annotated[
        list[str], Meta(description="Only update items with these ids")
    ]
    sort: Annotated[
        str,
        Meta(description='Sort order as comma separated list, e.g. "+year,-title"'),
    ]
    limit: Annotated[
        int, Meta(description="Page size, i.e. maximum number of items to update")
    ]


@items_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkPatchQueryParams)
@validate_request(ItemAttributes)
@validate_response(MultiItemDocument)
@error_responses(InvalidUsageException, NotImplementedException)
async def patch_items(
    query_args: BulkPatchQueryParams, data: ItemAttributes
) -> MultiItemDocument:
    """Patch items (bulk)

    Update the attributes of all items matching the given filters.

    Not implemented yet - currently returns 501.
    """
    raise NotImplementedException


class BulkDeleteQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the items")
    ]
    filter_ids: Annotated[
        list[str], Meta(description="Only delete items with these ids")
    ]
    delete_file: Annotated[
        bool, Meta(description="Also delete the item's file from disk")
    ]


@items_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
@error_responses(InvalidUsageException, NotImplementedException)
async def delete_items(query_args: BulkDeleteQueryParams):
    """Delete items (bulk)

    Delete all items matching the given filters.

    Not implemented yet - currently returns 501.
    """
    raise NotImplementedException
