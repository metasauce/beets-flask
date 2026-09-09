from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from pydantic import BaseModel, BeforeValidator, Field, model_validator
from quart import Blueprint, request
from quart_schema import validate_querystring, validate_request, validate_response

from beets_flask.importer.types import BeetsItem
from beets_flask.server.exceptions import InvalidUsageError, NotFoundError
from beets_flask.server.routes_next.beets._query import (
    PaginatedQuery,
    build_filter_query,
)

from ..jsonapi import LinkObject, MetaObject, error_responses
from . import g
from ._types import (
    BulkFilterQueryParams,
    BulkResult,
    Cursor,
    Direction,
    ItemAttributes,
    ItemResource,
    ItemSortField,
    MultiItemDocument,
    SingleItemDocument,
    Sort,
)

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


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(BulkFilterQueryParams):
    cursor: Annotated[
        Cursor[Sort[ItemSortField]] | None,
        Field(
            description=(
                "Pagination cursor from the ``links.next`` of a previous response. "
            ),
        ),
        BeforeValidator(
            Cursor[Sort[ItemSortField]].from_string, json_schema_input_type=str
        ),
    ] = None
    sort: Annotated[
        Sort[ItemSortField] | None,
        Field(
            description=(
                "Sort the results by one of: "
                + ", ".join(f"``{name}``" for name in ItemSortField.values())
                + ". Prefix ``-`` for descending or ``+`` "
                "for ascending."
            ),
        ),
        BeforeValidator(Sort[ItemSortField].from_str, json_schema_input_type=str),
    ] = None
    limit: Annotated[
        int,
        Field(description="Page size min 1, max 1000.", ge=1, le=1000),
    ] = 100

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

    def to_cursor(self) -> Cursor[Sort[ItemSortField]]:
        """Derive the page's cursor from the query params.

        Follow-up pages carry a decoded, self-contained ``cursor``; for the first
        page the cursor is built from ``sort`` (default ``-added``) and the
        filters.
        """
        if self.cursor is not None:
            return self.cursor

        # Default: newest first (``-added``).
        sort = self.sort or Sort(field=ItemSortField.ADDED, direction=Direction.DESC)
        return Cursor(
            sort=sort,
            filter_query=self.filter_query,
            filter_ids=self.filter_ids,
        )


@items_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiItemDocument)
@error_responses(InvalidUsageError)
async def get_items(query_args: BulkGetQueryParams) -> MultiItemDocument:
    """Get items (bulk).

    Retrieve beets items filtered query or by ids.

    Use ``filter_query``/``filter_ids`` for the initial request and the self-contained
    ``cursor`` from ``links.next`` for the following pages.

    Cursor and filters are mutually exclusive.
    """
    cursor = query_args.to_cursor()
    limit = query_args.limit

    page = PaginatedQuery(cursor, table="items")
    rows = list(g.lib.items(page, page, limit=limit + 1))

    items = rows[:limit]
    links = LinkObject(self=request.url)
    if len(rows) > limit:
        last_item = items[-1]
        last_value = getattr(last_item, cursor.sort.field.value, None)
        token = cursor.next(
            None if last_value is None else str(last_value), last_item.id
        ).to_string()
        links.next = (
            request.base_url + "?" + urlencode({"cursor": token, "limit": limit})
        )

    return MultiItemDocument(
        data=[to_item_resource(item) for item in items],
        links=links,
        meta=MetaObject(total=page.total(g.lib)),
    )


@items_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkFilterQueryParams)
@validate_request(ItemAttributes)
@validate_response(BulkResult)
@error_responses(InvalidUsageError)
async def patch_items(
    query_args: BulkFilterQueryParams, data: ItemAttributes
) -> BulkResult:
    """Patch items (bulk).

    Update the attributes of all items matching the given filters. The change is applied
    to the beets library and written to the files' metadata if applicable. Attributes
    that are not present in the body are left unchanged; an explicit ``null`` clears the
    field.
    """

    update_data = data.patch_data()
    query = build_filter_query(
        query_args.filter_query, query_args.filter_ids, BeetsItem
    )

    # Update every matching item in a single transaction
    total = 0
    with g.lib.transaction():
        for item in g.lib.items(query):
            item.update(update_data)
            item.try_sync(True, False)
            total += 1

    return BulkResult(meta=MetaObject(total=total))


class BulkDeleteQueryParams(BulkFilterQueryParams):
    delete_files: Annotated[
        bool,
        Field(
            description="Also delete the item files on disk",
        ),
    ] = False


@items_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
@validate_response(BulkResult)
@error_responses(InvalidUsageError)
async def delete_items(query_args: BulkDeleteQueryParams) -> BulkResult:
    """Delete items (bulk).

    Delete all items matching the given filters. The items are removed
    from the library database. Pass ``delete_file=true`` to also remove
    their files from disk. If an item was the last one of its album,
    the album is removed as well.
    """

    query = build_filter_query(
        query_args.filter_query, query_args.filter_ids, BeetsItem
    )

    # Delete every matching item in a single transaction
    total = 0
    with g.lib.transaction():
        for item in g.lib.items(query):
            item.remove(delete=query_args.delete_files)
            total += 1

    return BulkResult(meta=MetaObject(total=total))
