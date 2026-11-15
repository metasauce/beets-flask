from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from beets.library import Item, parse_query_string

from beets_flask.config import get_config
from beets_flask.library_indexes import LIBRARY_INDEXES, ensure_library_indexes
from beets_flask.server.routes.library.resources import Cursor, PaginatedQuery

if TYPE_CHECKING:
    from beets.library import Library


def _index_names(lib: Library) -> set[str]:
    with lib.transaction() as tx:
        rows = tx.query("SELECT name FROM sqlite_master WHERE type = 'index'")
    return {row[0] for row in rows}


def _plan(lib: Library, sql: str, values=()) -> list[str]:
    with lib.transaction() as tx:
        return [row[3] for row in tx.query(f"EXPLAIN QUERY PLAN {sql}", values)]


def test_creates_indexes(beets_lib: Library):
    ensure_library_indexes(beets_lib)
    assert set(LIBRARY_INDEXES) <= _index_names(beets_lib)

    # Idempotent
    ensure_library_indexes(beets_lib)


def test_readonly_library_is_not_modified(beets_lib: Library):
    config = get_config()
    config.data.gui.library.readonly = True
    try:
        ensure_library_indexes(beets_lib)
    finally:
        config.data.gui.library.readonly = False

    assert not set(LIBRARY_INDEXES) & _index_names(beets_lib)


@pytest.mark.parametrize("direction", ["ASC", "DESC"])
@pytest.mark.parametrize("last", [(None, None), ("20.0", "20")])
def test_items_page_uses_index(beets_lib: Library, direction, last):
    """The page is read in index order, without sorting all items."""
    ensure_library_indexes(beets_lib)

    query = PaginatedQuery(
        Cursor("added", direction, *last),
        parse_query_string("", Item),
        n_items=10,
        table="items",
    )
    clause, values = query.clause()
    plan = _plan(beets_lib, f"SELECT * FROM items WHERE {clause}", values)

    assert any("beets_flask_items_added" in step for step in plan), plan
    # Only items with the same `added` value are sorted (by id), not all items
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan, plan


def test_stats_use_covering_index(beets_lib: Library):
    ensure_library_indexes(beets_lib)
    plan = _plan(
        beets_lib, "SELECT COUNT(*), MAX(added), MAX(mtime), SUM(length) FROM items"
    )
    assert plan == ["SCAN items USING COVERING INDEX beets_flask_items_added"]


def test_artists_use_covering_index(beets_lib: Library):
    ensure_library_indexes(beets_lib)
    plan = _plan(beets_lib, "SELECT artist, added FROM items")
    assert plan == ["SCAN items USING COVERING INDEX beets_flask_items_artist_added"]
