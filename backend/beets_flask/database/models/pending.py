from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .states import TaskStateInDb


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


class TaskItem(Base):
    __tablename__ = "tasks_items"

    task_id: Mapped[str] = mapped_column(ForeignKey("task.id"))
    task: Mapped[TaskStateInDb] = relationship(back_populates="pending_items")
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"))
    item: Mapped[Item] = relationship()

    def __init__(self, item: Item, id: str | None = None):
        super().__init__(id)
        self.item = item
