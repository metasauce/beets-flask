from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beets_flask.importer.types import BeetsItem

from .base import Base

if TYPE_CHECKING:
    from .states import TaskStateInDb


class TasksItems(Base):
    __tablename__ = "tasks_items"

    task_id: Mapped[str] = mapped_column(ForeignKey("task.id"))
    task: Mapped[TaskStateInDb] = relationship(back_populates="pending_items")
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"))
    item: Mapped[Item] = relationship()

    def __init__(self, item: Item, id: str | None = None):
        super().__init__(id)
        self.item = item


class Item(Base):
    __tablename__ = "items"

    # items table in beets db
    fixed_values: Mapped[dict[str, Any]] = mapped_column(JSON)

    # item_attributes table  in beets db
    flex_values: Mapped[dict[str, Any]] = mapped_column(JSON)

    def __init__(
        self,
        fixed_values: dict[str, Any],
        flex_values: dict[str, Any],
        id: str | None = None,
    ):
        super().__init__(id)
        self.fixed_values = fixed_values
        self.flex_values = flex_values

    # FIXME: Move to mapper layer after match migration!

    def to_beets(self):
        return BeetsItem._awaken(
            fixed_values={k: self._decode(v) for k, v in self.fixed_values.items()},
            flex_values={k: self._decode(v) for k, v in self.flex_values.items()},
        )

    @classmethod
    def from_beets(cls, obj: BeetsItem):
        return cls(
            fixed_values={k: cls._encode(v) for k, v in obj._values_fixed.items()},
            flex_values={k: cls._encode(v) for k, v in obj._values_flex.items()},
        )

    @classmethod
    def _encode(cls, v):
        if isinstance(v, bytes):
            return {
                "__type__": "bytes",
                "data": base64.b64encode(v).decode("ascii"),
            }

        if isinstance(v, dict):
            return {str(k): cls._encode(val) for k, val in v.items()}

        if isinstance(v, list):
            return [cls._encode(x) for x in v]

        return v

    @classmethod
    def _decode(cls, v):
        if isinstance(v, dict):
            if v.get("__type__") == "bytes":
                return base64.b64decode(v["data"])
            return {k: cls._decode(val) for k, val in v.items()}

        if isinstance(v, list):
            return [cls._decode(x) for x in v]

        return v

    def process_bind_param(self, value: BeetsItem | None, dialect):
        """Transform from live object into serialized json in database."""
        if value is None or not value:
            return None

        return {
            "fixed_values": {
                k: self._encode(v) for k, v in value._values_fixed.items() if v
            },
            "flex_values": {
                k: self._encode(v) for k, v in value._values_flex.items() if v
            },
        }

    def process_result_value(self, value, dialect):
        """Transform from serialized json in database to live object."""
        if value is None:
            return None

        return BeetsItem._awaken(
            fixed_values={
                k: self._decode(v) for k, v in value.get("fixed_values", {}).items()
            },
            flex_values={
                k: self._decode(v) for k, v in value.get("flex_values", {}).items()
            },
        )


class TaskPendingItem(Base):
    __tablename__ = "task_pending_items"

    task_id: Mapped[str] = mapped_column(ForeignKey("task.id"))
    task: Mapped[TaskStateInDb] = relationship(back_populates="pending_items")
    item: Mapped[BeetsItem] = mapped_column(BeetsItemType())

    def __init__(self, item: BeetsItem, id: str | None = None):
        super().__init__(id)
        self.item = item
