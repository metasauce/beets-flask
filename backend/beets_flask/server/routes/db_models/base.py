from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, TypeVar

from quart import Blueprint, request
from sqlalchemy import select

from beets_flask.database import db_session_factory
from beets_flask.database.models.base import Base
from beets_flask.server.routes.exception import InvalidUsageError
from beets_flask.server.utility import pop_query_param

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["ModelAPIBlueprint"]

T = TypeVar("T", bound=Base)


class ModelAPIBlueprint(Generic[T]):
    """Generic API blueprint for a model.

    Any database model can be used with this blueprint. Allows
    for easy CRUD operations on the model.
    """

    blueprint: Blueprint
    model: type[T]

    def __init__(self, model: type[T], url_prefix: str | None = None):
        # Use the model name as the default URL prefix
        if url_prefix is None:
            url_prefix = model.__name__.lower()

        self.model = model
        self.blueprint = Blueprint(
            url_prefix,
            __name__,
            url_prefix=url_prefix,
        )

        self._register_routes()

    def _register_routes(self) -> None:
        """Register the routes for the blueprint."""
        self.blueprint.route("/", methods=["GET"])(self.get_all)
        self.blueprint.route("/id/<id>", methods=["GET"])(self.get_by_id)
        self.blueprint.route("/id/<id>", methods=["DELETE"])(self.delete_by_id)

    async def get_all(self):
        params = dict(request.args)
        # Cursor is encoded as a string in the format "datetime,id" where date
        # is the creation date as integer and id is the id of the item.
        cursor = pop_query_param(
            params,
            "cursor",
            _cursor_from_string,
        )
        n_items = pop_query_param(
            params,
            "n_items",
            int,
            50,
        )

        items, next_cursor = _get_n_with_cursor(self.model, cursor, n_items)

        cursor_str = _cursor_to_string(next_cursor)

        if cursor_str is not None:
            next = f"{request.path}?cursor={cursor_str}&n_items={n_items}"
        else:
            next = None
        return {"items": items, "next": next}

    async def get_by_id(self, id: str):
        with db_session_factory() as session:
            item = self.model.get_by(self.model.id == id, session=session)
            if not item:
                raise InvalidUsageError(
                    f"Item with id {id} not found", status_code=404
                )

            return item.to_dict()

    async def delete_by_id(self, id: str):
        with db_session_factory() as session:
            item = self.model.get_by(self.model.id == id, session=session)
            if not item:
                return {"message": f"Item with id {id} not found"}, 200
            session.delete(item)
            session.commit()

        return {"message": f"Item with id {id} deleted successfully"}, 200


# ------------------------------- Local Utility ------------------------------ #


def _cursor_to_string(cursor: tuple[datetime, str] | None) -> str | None:
    if cursor is None:
        return None
    return f"{cursor[0].isoformat()},{cursor[1]}".encode().hex()


def _cursor_from_string(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    cursor = bytes.fromhex(cursor).decode("utf-8")
    c = cursor.split(",")
    if len(c) != 2:
        return None
    return datetime.fromisoformat(c[0]), c[1]


def _get_n_with_cursor(
    model: type[T], cursor: tuple[datetime, str] | None = None, n_items: int = 50
):
    """Seek pagination for all items in the database.

    Returns a list of items and a cursor for the next page.
    """

    with db_session_factory() as db_session:
        query = select(model)
        if cursor:
            query = query.where(
                # cursor is a combination of date and model id, this is faster than
                # just using an offset
                (model.created_at <= cursor[0]).__and__(model.id < cursor[1])
            )
        query = query.order_by(model.created_at.desc(), model.id.desc()).limit(n_items)
        items: Sequence[T] = db_session.execute(query).scalars().all()

        # Convert items to a list of dictionaries
        items_list = [item.to_dict() for item in items]

    # Determine the next cursor
    if len(items) == n_items:
        last_item = items[-1]
        next_cursor = (last_item.created_at, last_item.id)
    else:
        next_cursor = None

    return items_list, next_cursor
