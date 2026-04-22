from __future__ import annotations

from typing import TypedDict

from quart import Blueprint
from quart_schema import validate_querystring, validate_request
from quart_schema.validation import validate_response

from ._types import (
    ItemAttributes,
    MultiItemDocument,
    SingleItemDocument,
)

items_bp = Blueprint("items", __name__, url_prefix="/items")

# ---------------------------------- Single ---------------------------------- #


@items_bp.route("/<item_id>", methods=["GET"])
@validate_response(SingleItemDocument)
async def get_item(item_id: str) -> SingleItemDocument:
    """GET item - Retrieve a single beets item by ID"""
    return "foo"


@items_bp.route("/<item_id>", methods=["PATCH"])
@validate_request(ItemAttributes)
@validate_response(SingleItemDocument)
async def patch_item(item_id: str, data: ItemAttributes) -> SingleItemDocument:
    """PATCH item - Update a single beets item by ID"""
    return "bar"


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
    return "foo"


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
    return "bar"


class BulkDeleteQueryParams(TypedDict, total=False):
    filter_query: str
    filter_ids: list[str]
    delete_file: bool


@items_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
async def delete_items(query_args: BulkDeleteQueryParams):
    """DELETE items - Bulk delete beets items via filter"""
    return ""
