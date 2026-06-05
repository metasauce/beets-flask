"""Added item reference to TrackMatch

Revision ID: 25649aa3ba78
Revises: f06e470b3d1e
Create Date: 2026-05-20 21:20:11.140311

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "25649aa3ba78"
down_revision: str | Sequence[str] | None = "f06e470b3d1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("matches_track", sa.Column("item_id", sa.String(), nullable=False))
    op.create_foreign_key(
        "fk_matches_track_items", "matches_track", "items", ["item_id"], ["id"]
    )
    op.drop_column("candidate", "mapping")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_matches_track_items", "matches_track", type_="foreignkey")
    op.drop_column("matches_track", "item_id")
