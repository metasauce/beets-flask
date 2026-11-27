"""Index foreign keys

SQLite does not index foreign key columns by itself. Loading a session
lazy-loads its tasks, candidates, matches, distances and penalties by
these columns, so without an index every one of those loads scanned the
whole table. With a few hundred sessions that made opening a single
inbox folder take minutes.

Revision ID: 37ff7b5e3e3c
Revises: 7b11d6a3c6a7
Create Date: 2026-11-09 18:33:19.570084

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "37ff7b5e3e3c"
down_revision: str | Sequence[str] | None = "7b11d6a3c6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOREIGN_KEYS: list[tuple[str, str]] = [
    ("album_match_track_mappings", "album_match_id"),
    ("album_match_track_mappings", "item_id"),
    ("album_match_track_mappings", "track_info_id"),
    ("candidate", "match_id"),
    ("candidate", "task_id"),
    ("distances", "parent_distance_id"),
    ("distances", "track_info_id"),
    ("matches", "distance_id"),
    ("matches_album", "info_id"),
    ("matches_track", "info_id"),
    ("matches_track", "item_id"),
    ("penalties", "distance_id"),
    ("task", "chosen_candidate_id"),
    ("task", "session_id"),
    ("tasks_items", "item_id"),
    ("tasks_items", "task_id"),
    ("track_info", "album_id"),
]


def upgrade() -> None:
    """Upgrade schema."""
    for table, column in FOREIGN_KEYS:
        # if_not_exists: the indexes may have been created by hand already
        op.create_index(
            op.f(f"ix_{table}_{column}"),
            table,
            [column],
            unique=False,
            if_not_exists=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table, column in reversed(FOREIGN_KEYS):
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table, if_exists=True)
