from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from beets_flask.importer.types import BeetsItem

from .base import Base

if TYPE_CHECKING:
    from .states import TaskStateInDb


class BeetsItemType(TypeDecorator[BeetsItem]):
    """
    We do not implement items in full detail yet, but keep them as a serialized json.

    The transformation is relatively short, because items in beets are already
    in a format for (their) database.

    Notes:
    - this type is relevant, because we want to save items __before__ beets does, so
      that we can resume imports.
    - in beets, the fixed_ and flex_values are computed at runtime and not stored
      1:1 in beets' internal library:
        - fixed are their own columns
        - flex are linked in an extra table
    - we need them here, but not as pickle (no need for functions/classes, and including
      functions etc makes migrations a lot harder)
    """

    impl = JSON

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
                k: self._encode(v) for k, v in value._values_fixed.items()
            },
            "flex_values": {k: self._encode(v) for k, v in value._values_flex.items()},
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

    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"))
    task: Mapped[TaskStateInDb] = relationship(back_populates="pending_items")
    item: Mapped[BeetsItem] = mapped_column(BeetsItemType())

    def __init__(self, item: BeetsItem, id: str | None = None):
        super().__init__(id)
        self.item = item
