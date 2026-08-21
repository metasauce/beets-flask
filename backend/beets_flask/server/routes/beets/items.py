from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from quart import Blueprint, g
from quart_schema import validate_querystring, validate_request
from quart_schema.validation import validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BeetsItem
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


def get_item_resource(item: BeetsItem) -> ItemResource:
    return {
        "type": "item",
        "id": str(item.id),
        "attributes": {"title": item.title},
    }


# ---------------------------------- Single ---------------------------------- #


@items_bp.route("/<int:item_id>", methods=["GET"])
@validate_response(SingleItemDocument)
async def get_item(item_id: int) -> SingleItemDocument:
    """GET item - Retrieve a single beets item by ID"""
    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:{item_id!r} not found in beets db."
        )

    return {
        "data": get_item_resource(item),
    }


@items_bp.route("/<int:item_id>", methods=["PATCH"])
@validate_request(ItemAttributes)
@validate_response(SingleItemDocument)
async def patch_item(item_id: int, data: ItemAttributes) -> SingleItemDocument:
    """PATCH item - Update a single beets item by ID"""
    item = g.lib.get_item(item_id)
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
        "data": get_item_resource(item),
    }


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(TypedDict, total=False):
    cursor: str  # pagination cursor
    filter_query: str
    filter_ids: list[str]
    sort: str  # "+year,-title"
    limit: int  # page size


@items_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiItemDocument)
async def get_items(query_args: BulkGetQueryParams) -> MultiItemDocument:
    """GET items - Retrieve beets items

    Lets you retrieve beets items.
    """
    raise NotImplementedError


class BulkPatchQueryParams(TypedDict, total=False):
    filter_query: str
    filter_ids: list[str]
    sort: str  # "+year,-title"
    limit: int  # page size


@items_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkPatchQueryParams)
@validate_request(ItemAttributes)
@validate_response(MultiItemDocument)
async def patch_items(
    query_args: BulkPatchQueryParams, data: ItemAttributes
) -> MultiItemDocument:
    """PATCH items - Update beets items

    Lets you update beets items.
    """
    raise NotImplementedError


class BulkDeleteQueryParams(TypedDict, total=False):
    filter_query: str
    filter_ids: list[str]
    delete_file: bool


@items_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
async def delete_items(query_args: BulkDeleteQueryParams):
    """DELETE items - Bulk delete beets items via filter"""
    raise NotImplementedError
