from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, TypedDict
from urllib.parse import urlencode

from pydantic import Field
from quart import Blueprint, g, request
from quart_schema import validate_request, validate_response

from beets_flask.importer.types import BeetsItem
from beets_flask.server.exceptions import (
    InvalidUsageException,
    NotFoundException,
)
from beets_flask.server.utility import ensure_writable
from beets_flask.server.validation import validate_querystring

from ..jsonapi import LinkObject, MetaObject, error_responses
from ._cursor import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PaginatedQuery,
    build_cursor,
    build_filter_query,
)
from ._types import (
    BulkFilterParams,
    BulkResult,
    ItemAttributes,
    ItemResource,
    ItemSort,
    ItemSortField,
    MultiItemDocument,
    SingleItemDocument,
)

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

items_bp = Blueprint("items", __name__, url_prefix="/items")


def to_item_resource(item: BeetsItem) -> ItemResource:
    attributes = ItemAttributes(
        title=item.title,
        artist=item.artist,
    )
    # TODO: allow for source plugin adapter specific extraction
    # if data_source == "musibrainz:"

    return ItemResource(
        type="item",
        id=str(item.id),
        attributes=attributes,
    )


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

    return SingleItemDocument(data=to_item_resource(item))


# Attributes that cannot be set via PATCH
READ_ONLY_ITEM_ATTRIBUTES = frozenset({"album_id", "added", "size", "path", "sources"})


@items_bp.route("/<int:item_id>", methods=["PATCH"])
@validate_request(ItemAttributes)
@validate_response(SingleItemDocument)
@error_responses(InvalidUsageException, NotFoundException)
async def patch_item(item_id: int, data: ItemAttributes) -> SingleItemDocument:
    """Patch item

    Update the attributes of a single item, e.g. its title. The change
    is written back to the beets library and to disk (if applicable).
    Attributes that are not present in the body are left unchanged; an
    explicit ``null`` clears the field.

    Returns 400 if the library is configured as read-only.
    """
    item: BeetsItem = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:{item_id!r} not found in beets db."
        )

    ensure_writable()

    # ``model_fields_set`` are the attributes present in the request body:
    # absent fields are left unchanged, an explicit ``null`` clears the
    # field. Read-only attributes (e.g. ``path``, ``sources``) are derived
    # from the library state and cannot be set by clients; ignore them.
    update_data = {
        k: getattr(data, k)
        for k in data.model_fields_set
        if k not in READ_ONLY_ITEM_ATTRIBUTES
    }
    if update_data:
        item.update(update_data)
        item.try_sync(True, False)

    return SingleItemDocument(data=to_item_resource(item))


class DeleteQueryParams(TypedDict, total=False):
    delete_file: Annotated[
        bool,
        Field(
            description="Also delete the item's file from disk",
            json_schema_extra={"default": False},
        ),
    ]


@items_bp.route("/<int:item_id>", methods=["DELETE"])
@validate_querystring(DeleteQueryParams)
@validate_response(SingleItemDocument)
@error_responses(InvalidUsageException, NotFoundException)
async def delete_item(
    item_id: int, query_args: DeleteQueryParams
) -> SingleItemDocument:
    """Delete item

    Delete a single item from the beets library. The item is removed
    from the library database; pass ``delete_file=true`` to also remove
    its file from disk. If the item was the last one of its album, the
    album is removed as well.

    Returns 400 if the library is configured as read-only.
    """
    item: BeetsItem = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:{item_id!r} not found in beets db."
        )

    ensure_writable()

    resource = to_item_resource(item)
    item.remove(delete=query_args.get("delete_file", False))
    return SingleItemDocument(data=resource)


# ----------------------------------- Bulk ----------------------------------- #


class BulkGetQueryParams(BulkFilterParams, total=False):
    cursor: Annotated[
        str,
        Field(
            description=(
                "Pagination cursor from the ``links.next`` of a previous "
                "response. The cursor is self-contained: it encodes the sort "
                "and the filters of the original request, so the following "
                "pages only need the cursor (plus an optional ``limit``). "
                "Cannot be combined with ``sort``, ``filter_query`` or "
                "``filter_ids``."
            )
        ),
    ]
    sort: Annotated[
        ItemSort,
        Field(
            description=(
                'Sort by a field, optionally prefixed with "+" (ascending) or '
                '"-" (descending), e.g. "+title". Default: "-added".'
            ),
            examples=["+title"],
            json_schema_extra={"default": "-added"},
        ),
    ]
    limit: Annotated[
        int,
        Field(
            description=(
                "Page size, i.e. maximum number of items to return. Defaults "
                "to 100; the minimum is 1, the maximum is 1000."
            ),
            json_schema_extra={"default": 100},
        ),
    ]


@items_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiItemDocument)
@error_responses(InvalidUsageException)
async def get_items(query_args: BulkGetQueryParams) -> MultiItemDocument:
    """Get items (bulk)

    Retrieve beets items matching the given filters, with pagination.

    **Filters**

    - ``filter_query``: a beets query string, e.g. ``artist:Tool``
    - ``filter_ids``: repeatable, explicit item ids

    The filters are combined with AND; without any filter, all items
    match.

    **Pagination**

    The result is sorted by ``sort`` (default ``-added``) and paginated
    with a keyset cursor. Request the first page with ``sort`` and the
    filters; the ``links.next`` of the response carries a self-contained
    cursor that encodes the sort and the filters, so the following pages
    only need that cursor (plus an optional ``limit``). The cursor cannot
    be combined with ``sort`` or the filters.

    ``meta.total`` is the total number of matching items, independent of
    the page size.

    For example, the 50 most recently added tracks by Tool:
    ``GET /api_v1/beets/items/?filter_query=artist:Tool&limit=50``
    """
    # Construct cursor either from args or from the encoded cursor string.
    cursor = build_cursor(query_args, ItemSortField.values())

    # Limit is independent from cursor
    limit = query_args.get("limit", DEFAULT_LIMIT)
    if limit < 1:
        raise InvalidUsageException("limit must be positive")
    if limit > MAX_LIMIT:
        raise InvalidUsageException(f"limit must not exceed {MAX_LIMIT}")

    query = PaginatedQuery(cursor, limit + 1, "items")
    rows = list(g.lib.items(query, query))
    has_next = len(rows) > limit
    items = rows[:limit]

    # Create pagination links. The "next" link is only present if there
    # are more items to fetch.
    links = LinkObject(self=request.url)
    if has_next:
        cursor_token = cursor.next_from_entity(items[-1]).to_string()
        links.next = (
            request.base_url + "?" + urlencode({"cursor": cursor_token, "limit": limit})
        )

    return MultiItemDocument(
        data=[to_item_resource(item) for item in items],
        links=links,
        meta=MetaObject(total=query.total(g.lib)),
    )


class BulkPatchQueryParams(BulkFilterParams, total=False):
    """Query parameters of the bulk PATCH endpoint."""


@items_bp.route("/", methods=["PATCH"])
@validate_querystring(BulkPatchQueryParams)
@validate_request(ItemAttributes)
@validate_response(BulkResult)
@error_responses(InvalidUsageException)
async def patch_items(
    query_args: BulkPatchQueryParams, data: ItemAttributes
) -> BulkResult:
    """Patch items (bulk)

    Update the attributes of all items matching the given filters. The
    change is applied to the beets library and written to the files'
    tags, like the single item patch. Attributes that are not present
    in the body are left unchanged; an explicit ``null`` clears the
    field.

    The ``filter_query`` and ``filter_ids`` parameters are combined
    with AND; without any filter, all items match. All updates run in
    a single transaction and are committed together.

    Returns 400 if the library is configured as read-only or the body
    does not contain any attributes.
    """
    ensure_writable()

    query = build_filter_query(
        query_args.get("filter_query"), query_args.get("filter_ids"), BeetsItem
    )

    # ``model_fields_set`` are the attributes present in the request body:
    # absent fields are left unchanged, an explicit ``null`` clears.
    if not data.model_fields_set:
        raise InvalidUsageException("No attributes to update")

    # Read-only attributes (e.g. ``path``, ``sources``) are derived from
    # the library state and cannot be set by clients; ignore them.
    update_data = {
        k: getattr(data, k)
        for k in data.model_fields_set
        if k not in READ_ONLY_ITEM_ATTRIBUTES
    }
    if not update_data:
        raise InvalidUsageException("No attributes to update")

    # Update every matching item in a single transaction: the database
    # writes are committed together. If an update fails midway, the
    # already-written files stay consistent with the committed database
    # state, and the error propagates.
    total = 0
    with g.lib.transaction():
        for item in g.lib.items(query):
            item.update(update_data)
            item.try_sync(True, False)
            total += 1

    return BulkResult(meta=MetaObject(total=total))


class BulkDeleteQueryParams(BulkFilterParams, total=False):
    delete_file: Annotated[
        bool,
        Field(
            description="Also delete the item's file from disk",
            json_schema_extra={"default": False},
        ),
    ]


@items_bp.route("/", methods=["DELETE"])
@validate_querystring(BulkDeleteQueryParams)
@validate_response(BulkResult)
@error_responses(InvalidUsageException)
async def delete_items(query_args: BulkDeleteQueryParams) -> BulkResult:
    """Delete items (bulk)

    Delete all items matching the given filters. The items are removed
    from the library database; pass ``delete_file=true`` to also remove
    their files from disk. If an item was the last one of its album,
    the album is removed as well (and with ``delete_file=true`` its
    art file, too).

    The ``filter_query`` and ``filter_ids`` parameters are combined
    with AND; without any filter, all items match. All deletions run in
    a single transaction and are committed together.

    Returns 400 if the library is configured as read-only.
    """
    ensure_writable()

    query = build_filter_query(
        query_args.get("filter_query"), query_args.get("filter_ids"), BeetsItem
    )

    # Delete every matching item in a single transaction: the database
    # writes are committed together. If a deletion fails midway, the
    # already-deleted files stay consistent with the committed database
    # state, and the error propagates.
    delete = query_args.get("delete_file", False)
    total = 0
    with g.lib.transaction():
        for item in g.lib.items(query):
            item.remove(delete=delete)
            total += 1

    return BulkResult(meta=MetaObject(total=total))
