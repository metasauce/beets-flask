"""Keyset pagination cursor for the beets library routes.

Implements cursor-based (a.k.a. keyset) pagination for the album and item
endpoints. Instead of offset-based paging (``OFFSET x LIMIT n``), each page
carries a compact, opaque cursor token that encodes the last seen row. The
next page is fetched with a keyset predicate on the primary sort field plus
the ``id`` tiebreaker, which stays stable even when rows are inserted or
removed between requests.

The cursor is:

- normalized to a single ``+field`` / ``-field`` sort key, see
  :meth:`Cursor.normalize_sort`
- serialized to a hex-encoded JSON token (see :meth:`Cursor.to_string` and
  :meth:`Cursor.from_string`), safe to use as an opaque URL query parameter
- restricted to an allow-list of sortable fields before use, see
  :meth:`Cursor.validate_sort_allowed`

Typical route usage::

    if (token := params.pop("cursor", None)) is not None:
        cursor = Cursor.from_string(token)
    else:
        cursor = Cursor.initial(sort)
    cursor.validate_sort_allowed(["added", "year", "title"])
    rows = execute(
        select(...)
        .where(cursor.keyset_where_clause())
        .order_by(cursor.order_by_clause())
        .limit(n)
    )
    next_cursor = cursor.next_from_entity(rows[-1])
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from beets.dbcore.query import AndQuery, InQuery, Query
from beets.dbcore.sort import Sort
from beets.library import LibModel, parse_query_string

from beets_flask.importer.types import BeetsAlbum, BeetsItem, BeetsLibrary
from beets_flask.server.exceptions import InvalidUsageException

# The model class of each paginated table, used to parse the filter
# query string with the correct field set.
_TABLE_MODELS = {"items": BeetsItem, "albums": BeetsAlbum}


def parse_filter_query(query_string: str, model_cls: type[LibModel]) -> Query:
    """Parse a beets query string into a :class:`Query`.

    Raises
    ------
    InvalidUsageException
        If the query string cannot be parsed, e.g. because a value does
        not match the type of its field (``year:notanumber``).
    """
    try:
        query, _ = parse_query_string(query_string, model_cls)
    except ValueError as exc:
        raise InvalidUsageException(f"Invalid filter_query: {exc}") from exc
    return query


@dataclass(slots=True)
class Cursor:
    """Keyset cursor that encodes the full query state.

    Encapsulates everything needed to fetch the next page of results:

    - ``sort``: the normalized primary sort key (e.g. ``+added`` or ``-year``)
    - ``filter_query``: the query string the page was fetched with
    - ``filter_ids``: the explicit ids the page was fetched with
    - ``last_sort_value``: the sort value of the last returned row
    - ``last_id``: the ``id`` of the last returned row, used as a stable
      tiebreaker for rows that share the same sort value

    Because the filters are part of the cursor, the query state cannot
    drift between pages - the client only needs to pass the cursor (and
    a page size) back. A cursor without ``last_sort_value`` /
    ``last_id`` (see :meth:`initial`) is unanchored and returns the
    first page.
    """

    sort: str
    last_sort_value: str | None
    last_id: int | None
    filter_query: str | None = None
    filter_ids: list[str] | None = None

    @staticmethod
    def normalize_sort(sort: str | None, default: str = "-added") -> str:
        """Normalize a sort value into a ``+field`` / ``-field`` key.

        Only the first sort key is used for cursor pagination; additional
        keys are ignored, as keyset pagination needs a single anchor field.

        Parameters
        ----------
        sort : str | None
            Comma-separated sort keys, e.g. ``"year,-title"``. ``None`` or an
            empty value falls back to ``default``.
        default : str
            Sort key to use when ``sort`` is missing or empty.

        Returns
        -------
        str
            A single sort key of the form ``+field`` or ``-field``.
        """
        if sort is None:
            return default

        value = sort.strip()
        if not value:
            return default

        # Keep first sort key only.
        first = value.split(",")[0].strip()
        if not first:
            return default

        if first[0] in {"+", "-"}:
            sign = first[0]
            field = first[1:].strip()
        else:
            # Default to ascending if no sign is provided.
            sign = "+"
            field = first

        if not field:
            raise ValueError("Sort field cannot be empty.")

        return f"{sign}{field}"

    def next_from_entity(self, entity: Any) -> Cursor:
        """Create the cursor for the page after ``entity``.

        Reads the sort field and ``id`` from the last row of the current
        page, producing an anchored cursor for the next page. The
        filters are carried over unchanged.

        Parameters
        ----------
        entity : Any
            The last row of the current page. Must expose ``id`` and an
            attribute named after the cursor's sort field.
        """
        value = getattr(entity, self.field, None)
        return Cursor(
            sort=self.sort,
            last_sort_value=None if value is None else str(value),
            last_id=int(getattr(entity, "id")),
            filter_query=self.filter_query,
            filter_ids=self.filter_ids,
        )

    @classmethod
    def initial(
        cls,
        sort: str | None,
        default_sort: str = "-added",
        *,
        filter_query: str | None = None,
        filter_ids: Sequence[int] | None = None,
    ) -> Cursor:
        """Create an unanchored cursor (first page) from an optional sort.

        Parameters
        ----------
        sort : str | None
            Raw API sort value, normalized by :meth:`normalize_sort`.
        default_sort : str
            Fallback sort key when ``sort`` is missing or empty.
        filter_query : str | None
            Query string the page is fetched with.
        filter_ids : Sequence[int] | None
            Explicit ids the page is fetched with; stored as strings in
            the cursor token (see :meth:`to_string`).
        """
        return cls(
            sort=cls.normalize_sort(sort, default=default_sort),
            last_sort_value=None,
            last_id=None,
            filter_query=filter_query,
            filter_ids=None if filter_ids is None else [str(i) for i in filter_ids],
        )

    @property
    def field(self) -> str:
        """Name of the primary sort field (without sign)."""
        return self.sort[1:]

    @property
    def descending(self) -> bool:
        """Whether the primary sort is descending (``-field``)."""
        return self.sort.startswith("-")

    def to_string(self) -> str:
        """Serialize the cursor to an opaque, hex-encoded token.

        The token is a compact JSON object (``s``, ``v``, ``i``, plus
        ``q``/``f`` for the filters when present) encoded as hex, so it
        can be passed around safely as a URL query parameter.
        """
        payload: dict[str, Any] = {
            "s": self.sort,
            "v": self.last_sort_value,
            "i": self.last_id,
        }
        if self.filter_query is not None:
            payload["q"] = self.filter_query
        if self.filter_ids is not None:
            payload["f"] = self.filter_ids
        return json.dumps(payload, separators=(",", ":")).encode("utf-8").hex()

    @staticmethod
    def from_string(token: str) -> Cursor:
        """Deserialize a token produced by :meth:`to_string`.

        Parameters
        ----------
        token : str
            Hex-encoded JSON cursor token.

        Returns
        -------
        Cursor
            The decoded cursor. Non-string sort values and ids are coerced
            to ``str`` / ``int`` so the token stays stable across backends.

        Raises
        ------
        ValueError
            If the token is malformed or cannot be decoded.
        """
        try:
            data = json.loads(bytes.fromhex(token).decode("utf-8"))

            sort = Cursor.normalize_sort(data["s"])
            last_sort_value = data.get("v")
            last_id = data.get("i")

            if last_sort_value is not None and not isinstance(last_sort_value, str):
                # Store as string to keep token stable across numeric/datetime backends.
                last_sort_value = str(last_sort_value)

            if last_id is not None:
                last_id = int(last_id)

            filter_ids = data.get("f")

            return Cursor(
                sort=sort,
                last_sort_value=last_sort_value,
                last_id=last_id,
                filter_query=data.get("q"),
                filter_ids=filter_ids,
            )
        except Exception as exc:
            raise ValueError(f"Invalid cursor string: {token}") from exc

    def validate_sort_allowed(self, allowed_fields: Iterable[str]) -> None:
        """Ensure the cursor's sort field is in ``allowed_fields``.

        Prevents clients from paginating by arbitrary fields (e.g. columns
        not backed by an index or not intended for public use).

        Raises
        ------
        ValueError
            If the sort field is not in the allow-list.
        """
        if self.field not in set(allowed_fields):
            raise ValueError(f"Sort field {self.field!r} is not allowed.")

    def keyset_where_clause(self) -> tuple[str, Sequence[Any]]:
        """Build the keyset pagination predicate and its bind values.

        Returns
        -------
        tuple[str, Sequence[Any]]
            A ``(sql_predicate, params)`` tuple for use in a ``WHERE``
            clause.

        Predicate semantics:
        - ASC:  ``(field > ?) OR (field = ? AND id > ?)``
        - DESC: ``(field < ?) OR (field = ? AND id < ?)``

        If the cursor is not anchored yet (no ``last_sort_value`` or
        ``last_id``), a no-op predicate is returned.
        """
        if self.last_sort_value is None or self.last_id is None:
            return "1=1", ()

        comparator: Literal["<", ">"] = "<" if self.descending else ">"
        field: str = self.field

        return (
            f"({field} {comparator} ?) OR ({field} = ? AND id {comparator} ?)",
            (
                self.last_sort_value,
                self.last_sort_value,
                self.last_id,
            ),
        )

    def order_by_clause(self) -> str:
        """Build the deterministic ``ORDER BY`` clause for keyset pagination.

        The primary sort field plus ``id`` as tiebreaker, both in the
        cursor's direction, keeps the ordering stable across pages.
        """
        direction = "DESC" if self.descending else "ASC"
        return f"{self.field} {direction}, id {direction}"


class PaginatedQuery(Query, Sort):
    """A beets query and sort that fetches a single page.

    Combines the :class:`Cursor`'s filters and keyset predicate and
    limits the result to one page. Because it implements both the
    ``Query`` and ``Sort`` interfaces, it can be passed directly to
    ``lib.items(query, sort)`` and beets takes care of building the SQL
    and materializing the models::

        paginated = PaginatedQuery(cursor, n_items=limit + 1)
        rows = list(lib.items(paginated, paginated))

    Parameters
    ----------
    cursor:
        The keyset cursor anchoring the page. Its filters and sort are
        used to build the query.
    n_items:
        Number of rows to fetch (pass ``limit + 1`` to detect a next page).
    table:
        The database table to query, ``"items"`` or ``"albums"``.
    """

    def __init__(
        self,
        cursor: Cursor,
        n_items: int,
        table: Literal["items", "albums"],
    ) -> None:
        self.cursor = cursor
        self.n_items = n_items
        self.table = table
        self.sub_query: Query | None = None
        filters: list[Query] = []
        if cursor.filter_query:
            filters.append(
                parse_filter_query(cursor.filter_query, _TABLE_MODELS[table])
            )
        if cursor.filter_ids:
            try:
                # The cursor stores ids as strings; the database stores ints.
                filters.append(InQuery("id", [int(i) for i in cursor.filter_ids]))
            except ValueError as exc:
                raise InvalidUsageException(f"Invalid filter_ids: {exc}") from exc
        if filters:
            self.sub_query = AndQuery(filters)

    def clause(self) -> tuple[str | None, Sequence[Any]]:
        """The WHERE clause: the filters AND the keyset predicate."""
        if self.sub_query is None:
            filter_clause: str = "1=1"
            filter_params: Sequence[Any] = ()
        else:
            sub_clause, filter_params = self.sub_query.clause()
            filter_clause = sub_clause or "1=1"
        keyset_clause, keyset_params = self.cursor.keyset_where_clause()
        return (
            f"({filter_clause}) AND ({keyset_clause})",
            [*filter_params, *keyset_params],
        )

    def order_clause(self) -> str:
        """The ORDER BY clause, including the page limit."""
        return f"{self.cursor.order_by_clause()} LIMIT {self.n_items}"

    def match(self, obj: Any) -> bool:  # noqa: ARG002
        """The SQL clause above already filters, so everything matches."""
        return True

    def total(self, lib: BeetsLibrary) -> int:
        """The total number of rows matching the filters (without keyset)."""
        if self.sub_query is None:
            filter_clause: str = "1=1"
            filter_params: Sequence[Any] = ()
        else:
            sub_clause, filter_params = self.sub_query.clause()
            filter_clause = sub_clause or "1=1"
        with lib.transaction() as tx:
            row = tx.query(
                f"SELECT COUNT(*) FROM {self.table} WHERE {filter_clause}",
                list(filter_params),
            )[0]
        return row[0]
