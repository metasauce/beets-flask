"""Added item reference to TrackMatch

Revision ID: 25649aa3ba78
Revises: f06e470b3d1e
Create Date: 2026-05-20 21:20:11.140311

"""

from collections.abc import Sequence

import sqlalchemy as sa

from beets_flask.logger import logging
from alembic import op

log = logging.getLogger("alembic.runtime.migration")


# revision identifiers, used by Alembic.
revision: str = "25649aa3ba78"
down_revision: str | Sequence[str] | None = "f06e470b3d1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("matches_track") as batch_op:
        batch_op.add_column(sa.Column("item_id", sa.String(), nullable=False))
        batch_op.create_foreign_key(
            "fk_matches_track_items", "items", ["item_id"], ["id"]
        )
    with op.batch_alter_table("candidate") as batch_op:
        batch_op.drop_column("mapping")

    dedup_items()


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_matches_track_items", "matches_track", type_="foreignkey")
    op.drop_column("matches_track", "item_id")


def dedup_items() -> None:
    """Collapse duplicate Item rows created when task.items and
    match.mapping keys were separate Python objects during serialization.
    Keeps the oldest row per (track, title) and updates all FK refs."""
    conn = op.get_bind()

    items = conn.execute(
        sa.text("""
            SELECT id,
                   json_extract(fixed_values, '$.track') AS track,
                   json_extract(fixed_values, '$.title') AS title
            FROM items
            ORDER BY created_at ASC
        """)
    ).fetchall()

    seen: dict[tuple, str] = {}  # (track, title) -> canonical_id
    orphan_map: dict[str, str] = {}  # orphan_id -> canonical_id
    for row in items:
        key = (row.track, row.title)
        if key in seen:
            orphan_map[row.id] = seen[key]
        else:
            seen[key] = row.id

    if not orphan_map:
        log.info("No duplicate Item rows found")
        return

    log.info("Deduping %d duplicate Item rows", len(orphan_map))

    # Batch updates in chunks of 500 to stay under SQLite parameter limits
    CHUNK = 500
    items_list = list(orphan_map.items())
    for start in range(0, len(items_list), CHUNK):
        chunk = dict(items_list[start : start + CHUNK])
        if start > 0:
            log.info("Deduping items %d / %d", start, len(orphan_map))

        # Build CASE expression with parameters
        cases = []
        params: dict[str, str] = {}
        for j, (orphan_id, canonical_id) in enumerate(chunk.items()):
            params[f"o{j}"] = orphan_id
            params[f"c{j}"] = canonical_id
            cases.append(f"WHEN :o{j} THEN :c{j}")
        case_expr = " ".join(cases)
        in_list = ", ".join(f":o{j}" for j in range(len(chunk)))

        conn.execute(
            sa.text(
                f"UPDATE tasks_items SET item_id = CASE item_id {case_expr} "
                f"END WHERE item_id IN ({in_list})"
            ),
            params,
        )
        conn.execute(
            sa.text(
                f"UPDATE album_match_track_mappings SET item_id = "
                f"CASE item_id {case_expr} END WHERE item_id IN ({in_list})"
            ),
            params,
        )
        conn.execute(
            sa.text(f"DELETE FROM items WHERE id IN ({in_list})"),
            params,
        )

    log.info("Deduped %d duplicate Item rows", len(orphan_map))
