"""Indexes on the beets library that the library views rely on.

beets only indexes the album id and the flexible attribute tables. Paging
items ordered by `added` and aggregating artists then need a full scan of the
`items` table, which takes seconds for large libraries since its rows are wide
(lyrics, comments, ...), as do the item counts of the library stats. These
indexes make them independent of the library size.

Creating them on a large library takes a few seconds once, so this runs at
container startup and not within a request.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from beets_flask.logger import log

if TYPE_CHECKING:
    from beets.library import Library

LIBRARY_INDEXES: dict[str, str] = {
    # /library/items is ordered by `added, id`; mtime and length make it a
    # covering index for the item counts of /library/stats
    "beets_flask_items_added": "items (added, id, mtime, length)",
    # /library/artists reads only these two columns of every item
    "beets_flask_items_artist_added": "items (artist, added)",
}


def ensure_library_indexes(lib: Library | None = None) -> None:
    """Create the indexes if they do not exist yet.

    Does nothing if the library is configured as read-only, and only logs
    if the database cannot be written.
    """
    from beets.ui import _open_library

    from beets_flask.config import get_config

    config = get_config()
    if config.data.gui.library.readonly:
        log.debug("Library is read-only, not creating library indexes")
        return

    if lib is None:
        lib = _open_library(config.beets_config)

    try:
        with lib.transaction() as tx:
            for name, columns in LIBRARY_INDEXES.items():
                tx.mutate(f"CREATE INDEX IF NOT EXISTS {name} ON {columns}")
    except sqlite3.OperationalError as e:
        log.warning(f"Could not create library indexes: {e}")
