"""Drop task cur_artist and cur_album

Since beets 2.14 the current artist and album are no longer stored on
the task, but derived from its items via `ImportTask.source`:
`Source.from_items` calls the same `get_most_common_tags` that beets <
2.14 used to populate `cur_artist` / `cur_album`.

The dropped values are a pure function of the task's items, which are
persisted losslessly in `items` / `tasks_items` and restored together
with the task, so nothing is backfilled: the source is recomputed on
demand after loading.

Revision ID: 7b11d6a3c6a7
Revises: 25649aa3ba78
Create Date: 2026-09-10 18:00:04.303442

"""

from __future__ import annotations


import sqlalchemy as sa

from alembic import op
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7b11d6a3c6a7"
down_revision: str | Sequence[str] | None = "25649aa3ba78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_column("cur_artist")
        batch_op.drop_column("cur_album")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("task") as batch_op:
        batch_op.add_column(sa.Column("cur_artist", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("cur_album", sa.String(), nullable=True))
