"""item pending

Revision ID: 925cf8989fbc
Revises: a986c03d9ba3
Create Date: 2026-04-12 18:47:43.218344

README:
Historically, task state items were stored as binary (pickle) blobs in the database.
This approach has proven to be brittle and difficult to maintain. In particular,
changes and upgrades in beets break deserialization, requiring manual
intervention to recover or migrate data.
"""

from collections.abc import Sequence
from datetime import datetime
import io
import pickle
from uuid import uuid4

import sqlalchemy as sa
from beets_flask import log
from beets_flask.database.models.pending import BeetsItemType
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "925cf8989fbc"
down_revision: str | Sequence[str] | None = "a986c03d9ba3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class ModelStub:
    def __init__(self, *args, **kwargs):
        self._values_fixed = {}
        self._values_flex = {}
        self._db = None

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._model_cls = None  # must be reattached externally

    def __getstate__(self):
        return self.__dict__

    # --- mimic beets resolution ---
    def __getitem__(self, key):
        if "_values_fixed" in self.__dict__ and key in self._values_fixed:
            return self._values_fixed[key]

        if "_values_flex" in self.__dict__ and key in self._values_flex:
            return self._values_flex[key]

        if key in self.__dict__:
            return self.__dict__[key]

        raise KeyError(key)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        # keep internal structure intact
        if name in ("_values_fixed", "_values_flex", "_db"):
            self.__dict__[name] = value
        else:
            self.__dict__[name] = value


class LazyConvertDictStub:
    def __init__(self, *args, **kwargs):
        self._data = {}
        self._converted = {}
        self.model_cls = None  # Don't enforce model_cls, keep it flexible

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.model_cls = None

    def __getstate__(self):
        return self.__dict__

    def __getitem__(self, key):
        if key in self._converted:
            return self._converted[key]
        if key in self._data:
            return self._data[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        self._converted[key] = value

    def __contains__(self, key):
        return key in self._converted or key in self._data

    def keys(self):
        return list(self._converted.keys()) + list(self._data.keys())

    def __iter__(self):
        return iter(self.keys())

    def items(self):
        for key in self:
            yield key, self[key]


class ItemsUnpickler(pickle.Unpickler):
    CLASS_MAP = {
        ("beets.dbcore.db", "LazyConvertDict"): LazyConvertDictStub,
        ("beets.library", "Item"): ModelStub,
        ("beets.library.models", "Item"): ModelStub,
    }

    def find_class(self, module, name):
        """Override the find_class method to redirect Distance class references."""
        key = (module, name)
        if key not in self.CLASS_MAP:
            print(f"WARNING: Unknown class not in migration map: {module}.{name}")
            return dict  # Fallback for unknown classes
        return self.CLASS_MAP[key]


def load_items(blob: bytes) -> list[ModelStub]:
    return ItemsUnpickler(io.BytesIO(blob)).load()


def migrate_data():
    conn = op.get_bind()
    meta = sa.MetaData()

    task_pending_items = sa.Table("task_pending_items", meta, autoload_with=conn)

    result = conn.execute(sa.text("SELECT id, items FROM task WHERE items IS NOT NULL"))
    for row in result:
        task_id = row[0]
        items_blob = row[1]

        try:
            items = load_items(items_blob)
        except Exception as e:
            log.error(f"Failed to unpickle task {task_id}: {e}")
            continue

        rows = []
        now = datetime.utcnow()
        for stub in items:
            rows.append(
                {
                    "id": str(uuid4()),
                    "created_at": now,
                    "updated_at": now,
                    "task_id": task_id,
                    "item": {
                        "fixed_values": BeetsItemType._encode(
                            dict(stub._values_fixed.items())
                        ),
                        "flex_values": BeetsItemType._encode(
                            dict(stub._values_flex.items())
                        ),
                    },
                }
            )

        if rows:
            conn.execute(
                task_pending_items.insert(),
                rows,
            )


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "task_pending_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("item", BeetsItemType(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.id"],
        ),
    )
    op.create_index(
        op.f("ix_task_pending_items_created_at"),
        "task_pending_items",
        ["created_at"],
        unique=False,
    )

    migrate_data()

    op.drop_column("task", "items")
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("task", sa.Column("items", sa.BLOB(), nullable=False))
    op.drop_table("task_pending_items")
    # ### end Alembic commands ###
