from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Self
from uuid import uuid4

from sqlalchemy import LargeBinary, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    reconstructor,
    registry,
)
from sqlalchemy.sql import func

from beets_flask.logger import log

from .types import DictType, IntDictType, StrDictType


class Base(DeclarativeBase):
    __abstract__ = True

    registry = registry(
        type_annotation_map={
            bytes: LargeBinary,
            dict[int, int]: IntDictType,
            dict[str, str]: StrDictType,
            dict[str, Any]: DictType,
        }
    )

    id: Mapped[str] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    def __init__(self, id: str | None = None):
        self.id = str(id) if id is not None else str(uuid4())

    @classmethod
    def get_by(cls, *whereclause, session: Session | None = None) -> Self | None:
        close_after = False
        if session is None:
            log.debug(
                "No session provided, you will not be able to make changes to the database."
            )
            close_after = True
            from beets_flask.database.setup import session_factory

            session = session_factory()

        try:
            stmt = select(cls).where(*whereclause)
            item = session.execute(stmt).scalars().first()
            return item
        except:
            raise
        finally:
            if close_after:
                session.close()

    @classmethod
    def get_all_by(cls, *whereclause, session: Session | None = None) -> Sequence[Self]:
        close_after = False
        if session is None:
            log.debug(
                "No session provided, you will not be able to make changes to the database."
            )
            close_after = True
            from beets_flask.database.setup import session_factory

            session = session_factory()

        try:
            stmt = select(cls).where(*whereclause)
            item = session.execute(stmt).scalars().all()
            return item
        except:
            raise
        finally:
            if close_after:
                session.close()

    @classmethod
    def get_by_raise(cls, *whereclause, session: Session | None = None) -> Self:
        """Get an item by whereclause or raise ValueError if not found."""
        item = cls.get_by(*whereclause, session=session)
        if item is None:
            raise ValueError(f"{cls.__name__} not found.")
        return item

    @classmethod
    def exist_all_ids(cls, ids: list[str], session: Session) -> bool:
        """Check if an item exists for every given id."""
        _ids = set(ids)
        stmt = select(func.count()).select_from(cls).where(cls.id.in_(_ids))
        count = session.execute(stmt).scalar()
        if count is None or count != len(_ids):
            return False
        return True

    def to_dict(self) -> Mapping:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @reconstructor
    def _sqlalchemy_reconstructor(self):
        # Set timezone info for created_at and updated_at
        # Seems a bit hacky but is the only way to ensure that
        # datetime objects are timezone-aware after deserialization
        if self.created_at and self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.updated_at and self.updated_at.tzinfo is None:
            self.updated_at = self.updated_at.replace(tzinfo=UTC)
