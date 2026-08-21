from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal, TypeAlias, TypedDict
from urllib.parse import urlencode

from msgspec import Meta
from quart import Blueprint, g, request
from quart_schema import validate_request
from quart_schema.validation import validate_response

from beets_flask.config import get_config
from beets_flask.importer.types import BeetsItem
from beets_flask.server.exceptions import NotImplementedException, error_responses
from beets_flask.server.routes.exception import InvalidUsageException, NotFoundException

from ._cursor import Cursor, PaginatedQuery
from ._types import (
    ItemAttributes,
    ItemResource,
    LinkObject,
    MultiItemDocument,
    SingleItemDocument,
)
from ._validation import validate_querystring

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

items_bp = Blueprint("items", __name__, url_prefix="/items")

#: Default page size of the bulk endpoints.
DEFAULT_LIMIT = 100

#: Maximum allowed page size of the bulk endpoints.
MAX_LIMIT = 1000

#: The bare sortable field names of the bulk endpoints.
SORTABLE_FIELDS = (
    "added",
    "year",
    "title",
    "artist",
    "albumartist",
    "album",
    "track",
    "disc",
    "length",
    "bitrate",
)

#: All allowed ``sort`` values: a sortable field, optionally prefixed
#: with "+" (ascending) or "-" (descending). The prefixes are generated
#: programmatically from :data:`SORTABLE_FIELDS`.
SortableField: TypeAlias = Literal[  # type: ignore[valid-type]
    *(entry for field in SORTABLE_FIELDS for entry in (field, f"+{field}", f"-{field}"))
]  # mypy does not support PEP 646 star-unpacking in Literal yet


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


class DeleteQueryParams(TypedDict, total=False):
    delete_file: Annotated[
        bool,
        Meta(
            description="Also delete the item's file from disk",
            extra_json_schema={"default": False},
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
    """
    item: BeetsItem = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:{item_id!r} not found in beets db."
        )

    if get_config().data.gui.library.readonly:
        raise InvalidUsageException("Library is read-only")

    resource = to_item_resource(item)
    item.remove(delete=query_args.get("delete_file", False))
    return {
        "data": resource,
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
        SortableField,
        Meta(
            description='Sort by a field, optionally prefixed with "+" '
            '(ascending) or "-" (descending), e.g. "+title"'
        ),
    ]
    limit: Annotated[
        int, Meta(description="Page size, i.e. maximum number of items to return")
    ]


@items_bp.route("/", methods=["GET"])
@validate_querystring(BulkGetQueryParams)
@validate_response(MultiItemDocument)
@error_responses(InvalidUsageException)
async def get_items(query_args: BulkGetQueryParams) -> MultiItemDocument:
    """Get items (bulk)

    Retrieve beets items matching the given filters, with pagination.

    The result is sorted by ``sort`` (default ``-added``) and paginated
    with a keyset cursor. The cursor is self-contained: it encodes the
    sort and the filters, so pass ``sort``, ``filter_query`` and
    ``filter_ids`` for the first page and only the ``cursor`` (plus
    ``limit``) for the following pages.

    The function first builds the cursor - either a fresh one from the
    given sort and filters, or the encoded cursor of a following page -
    and then fetches the page using that cursor.
    """
    # Construct cursor either from args or from the encoded cursor string.
    # The cursor is self-contained
    if "cursor" in query_args and any(
        query_args.get(p) for p in ("sort", "filter_query", "filter_ids")
    ):
        raise InvalidUsageException("cursor cannot be combined with sort or filters")

    try:
        if cursor_token := query_args.get("cursor"):
            # Re-validate the sort: the token is client-supplied and
            # bypasses the sort enum above.
            cursor = Cursor.from_string(cursor_token)
            cursor.validate_sort_allowed(SORTABLE_FIELDS)
        else:
            cursor = Cursor.initial(
                query_args.get("sort"),
                filter_query=query_args.get("filter_query"),
                filter_ids=query_args.get("filter_ids"),
            )
    except ValueError as exc:
        raise InvalidUsageException(str(exc)) from exc

    # Limit is independent from cursor
    limit = query_args.get("limit") or DEFAULT_LIMIT
    if limit > MAX_LIMIT:
        raise InvalidUsageException(f"limit must not exceed {MAX_LIMIT}")

    query = PaginatedQuery(cursor, limit + 1, "items")
    rows = list(g.lib.items(query, query))
    has_next = len(rows) > limit
    items = rows[:limit]

    # Create pagination links. The "next" link is only present if there
    # are more items to fetch.
    links: LinkObject = {"self": request.url}
    if has_next:
        cursor_token = cursor.next_from_entity(items[-1]).to_string()
        links["next"] = (
            request.base_url + "?" + urlencode({"cursor": cursor_token, "limit": limit})
        )

    return {
        "data": [to_item_resource(item) for item in items],
        "links": links,
        "meta": {"total": query.total(g.lib)},
    }


class BulkPatchQueryParams(TypedDict, total=False):
    filter_query: Annotated[
        str, Meta(description="Beets query string to filter the items")
    ]
    filter_ids: Annotated[
        list[str], Meta(description="Only update items with these ids")
    ]
    sort: Annotated[
        SortableField,
        Meta(
            description='Sort by a field, optionally prefixed with "+" '
            '(ascending) or "-" (descending), e.g. "+title"'
        ),
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
        bool,
        Meta(
            description="Also delete the item's file from disk",
            extra_json_schema={"default": False},
        ),
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
