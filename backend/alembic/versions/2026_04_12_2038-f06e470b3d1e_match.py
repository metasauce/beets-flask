"""match

Revision ID: f06e470b3d1e
Revises: 925cf8989fbc
Create Date: 2026-04-12 20:38:28.263069

README:
Historically, candidate states included a pickled match item. This approach has proven
to be brittle and difficult to maintain. This migration implements a more refined
database schema for matches.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from beets_flask.database.models import types
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f06e470b3d1e"
down_revision: str | Sequence[str] | None = "925cf8989fbc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # core info table
    op.create_table(
        "album_info",
        sa.Column("data", types.DictType(), nullable=False),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_album_info_created_at", "album_info", ["created_at"])

    op.create_table(
        "track_info",
        sa.Column("album_id", sa.String(), sa.ForeignKey("album_info.id")),
        sa.Column("data", types.DictType(), nullable=False),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_track_info_created_at", "track_info", ["created_at"])

    # distance graph
    op.create_table(
        "distances",
        sa.Column("track_info_id", sa.String(), sa.ForeignKey("track_info.id")),
        sa.Column("parent_distance_id", sa.String(), sa.ForeignKey("distances.id")),
        sa.Column("raw_distance", sa.Float(), nullable=False),
        sa.Column("max_distance", sa.Float(), nullable=False),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # matches
    op.create_table(
        "matches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("distance_id", sa.String(), sa.ForeignKey("distances.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "matches_album",
        sa.Column("id", sa.String(), sa.ForeignKey("matches.id"), primary_key=True),
        sa.Column(
            "info_id", sa.String(), sa.ForeignKey("album_info.id"), nullable=False
        ),
    )
    op.create_table(
        "matches_track",
        sa.Column("id", sa.String(), sa.ForeignKey("matches.id"), primary_key=True),
        sa.Column(
            "info_id", sa.String(), sa.ForeignKey("track_info.id"), nullable=False
        ),
    )

    # mappings
    op.create_table(
        "album_match_track_mappings",
        sa.Column("album_match_id", sa.String(), sa.ForeignKey("matches_album.id")),
        sa.Column("track_info_id", sa.String(), sa.ForeignKey("track_info.id")),
        sa.Column("item", sa.LargeBinary()),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_album_match_track_mappings_created_at",
        "album_match_track_mappings",
        ["created_at"],
    )

    # penalties
    op.create_table(
        "penalties",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", types.FloatListType(), nullable=False),
        sa.Column(
            "distance_id", sa.String(), sa.ForeignKey("distances.id"), nullable=False
        ),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_penalties_created_at", "penalties", ["created_at"])
    op.create_index("ix_penalties_key", "penalties", ["key"])

    # TODO: data migrate
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM candidate"))

    with op.batch_alter_table("candidate") as batch_op:
        batch_op.drop_column("match")
        batch_op.add_column(sa.Column("match_id", sa.String(), nullable=False))
        batch_op.create_foreign_key(
            "fk_candidate_match",
            "matches",
            ["match_id"],
            ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""

    # candidate table (SQLite-safe)
    with op.batch_alter_table("candidate") as batch_op:
        batch_op.drop_constraint(
            "fk_candidate_match",
            type_="foreignkey",
        )
        batch_op.add_column(sa.Column("match", sa.BLOB(), nullable=True))
        batch_op.drop_column("match_id")

    # independent tables
    op.drop_table("matches_track")
    op.drop_table("matches_album")
    op.drop_table("album_match_track_mappings")

    op.drop_table("penalties")
    op.drop_table("matches")
    op.drop_table("distances")
    op.drop_table("track_info")
    op.drop_table("album_info")
