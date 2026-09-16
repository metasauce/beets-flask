"""Beets query helpers for the bulk endpoints.

- :func:`parse_filter_query` / :func:`build_filter_query`: turn the
  ``filter_query`` / ``filter_ids`` API arguments into a beets query.
- :func:`keyset_where_clause` / :func:`order_by_clause`: build the SQL of
  the keyset pagination predicate from a :class:`Cursor`.
- :class:`PaginatedQuery`: combines filters, keyset predicate and page
  limit into a single beets query + sort that fetches one page.
- :class:`PaginatedArtists`: the in-memory counterpart used by the derived
  artists resource, which only exists after splitting and aggregating.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from beets.dbcore.query import AndQuery, InQuery, Query
from beets.dbcore.sort import Sort as BeetsSort
from beets.library import LibModel, parse_query_string

from beets_flask.importer.types import BeetsAlbum, BeetsItem, BeetsLibrary
from beets_flask.server.exceptions import InvalidUsageError

from ._types import ArtistSortField, Direction

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._types import ArtistAttributes, Cursor, Sort

# The model class of each paginated table, used to parse the filter
# query string with the correct field set.
_TABLE_MODELS = {"items": BeetsItem, "albums": BeetsAlbum}


def parse_filter_query(query_string: str, model_cls: type[LibModel]) -> Query:
    """Parse a beets query string into a :class:`Query`.

    Raises
    ------
    InvalidUsageError
        If the query string cannot be parsed, e.g. because a value does
        not match the type of its field (``year:notanumber``).

    """
    try:
        query, _ = parse_query_string(query_string, model_cls)
    except ValueError as exc:
        raise InvalidUsageError(f"Invalid filter_query: {exc}") from exc
    return query


def build_filter_query(
    filter_query: str | None,
    filter_ids: Sequence[int | str] | None,
    model_cls: type[LibModel],
) -> Query | None:
    """Combine a ``filter_query`` string and explicit ids into an AND query.

    Returns ``None`` when neither is given.
    """
    filters: list[Query] = []
    if filter_query:
        filters.append(parse_filter_query(filter_query, model_cls))
    if filter_ids:
        try:
            filters.append(InQuery("id", [int(i) for i in filter_ids]))
        except ValueError as exc:
            raise InvalidUsageError(f"Invalid filter_ids: {exc}") from exc
    return AndQuery(filters) if filters else None


def keyset_where_clause(cursor: Cursor) -> tuple[str, Sequence[Any]]:
    """The keyset predicate of a cursor; no-op (``1=1``) if unanchored.

    ASC: ``(field > ?) OR (field = ? AND id > ?)``, DESC the analogous
    ``<`` variant. Returns a ``(sql, bind_params)`` pair.
    """
    if cursor.last_value is None or cursor.last_id is None:
        return "1=1", ()

    comparator: Literal["<", ">"] = (
        "<" if cursor.sort.direction == Direction.DESC else ">"
    )
    field = cursor.sort.field.value
    clause = f"({field} {comparator} ?) OR ({field} = ? AND id {comparator} ?)"
    return clause, (cursor.last_value, cursor.last_value, cursor.last_id)


class PaginatedQuery(Query, BeetsSort):
    """A beets query and sort that fetches a single page.

    Combines the :class:`Cursor`'s filters and keyset predicate and
    limits the result to one page. Because it implements both the
    ``Query`` and ``Sort`` interfaces, it can be passed directly to
    ``lib.items(query, sort)`` and beets takes care of building the SQL
    and materializing the models::

        paginated = PaginatedQuery(cursor)
        rows = list(lib.items(paginated, paginated))

    Parameters
    ----------
    cursor:
        The keyset cursor anchoring the page. Its filters and sort are
        used to build the query.
    table:
        The database table to query, ``"items"`` or ``"albums"``.

    """

    def __init__(
        self,
        cursor: Cursor,
        table: Literal["items", "albums"],
    ) -> None:
        self.cursor = cursor
        self.table = table
        self.sub_query = build_filter_query(
            cursor.filter_query, cursor.filter_ids, _TABLE_MODELS[table]
        )

    def clause(self) -> tuple[str | None, Sequence[Any]]:
        """The WHERE clause: the filters AND the keyset predicate."""
        if self.sub_query is None:
            filter_clause: str = "1=1"
            filter_params: Sequence[Any] = ()
        else:
            sub_clause, filter_params = self.sub_query.clause()
            filter_clause = sub_clause or "1=1"
        keyset_clause, keyset_params = keyset_where_clause(self.cursor)
        return (
            f"({filter_clause}) AND ({keyset_clause})",
            [*filter_params, *keyset_params],
        )

    def order_clause(self) -> str:
        """The ORDER BY clause, including the page limit."""
        # sort field + ``id`` tiebreaker
        direction = "DESC" if self.cursor.sort.direction == Direction.DESC else "ASC"
        return f"{self.cursor.sort.field.value} {direction}, id {direction}"

    def match(self, obj: Any) -> bool:
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


class PaginatedArtists:
    """Keyset pagination over the derived artists of the library.

    The in-memory counterpart of :class:`PaginatedQuery`: artists are not a
    beets model and only exist after splitting and aggregating, so sorting and
    the keyset filter happen on the aggregated records instead of in SQL. The
    cursor semantics are identical; the artist name is the unique tiebreaker,
    taking the place of the row id.
    """

    def __init__(
        self, cursor: Cursor[Sort[ArtistSortField]], records: list[ArtistAttributes]
    ) -> None:
        self.cursor = cursor
        self.records = records

    def _key(self, record: ArtistAttributes) -> tuple[Any, str]:
        return getattr(record, self.cursor.sort.field.value), record.artist

    def fetch(self, limit: int) -> list[ArtistAttributes]:
        """The next ``limit`` records after the cursor's anchor."""
        descending = self.cursor.sort.direction == Direction.DESC
        records = sorted(self.records, key=self._key, reverse=descending)

        if self.cursor.last_value is not None and self.cursor.last_id is not None:
            value: int | str = (
                int(self.cursor.last_value)
                if self.cursor.sort.field
                # The artist sort fields holding numeric values. Cursor anchors store
                # the last value as a string, so these have to be converted back.
                in {ArtistSortField.ALBUM_COUNT, ArtistSortField.ITEM_COUNT}
                else self.cursor.last_value
            )
            anchor = (value, str(self.cursor.last_id))
            if descending:
                records = [record for record in records if self._key(record) < anchor]
            else:
                records = [record for record in records if self._key(record) > anchor]

        return records[:limit]

    def total(self) -> int:
        """The total number of artists, independent of the page."""
        return len(self.records)
