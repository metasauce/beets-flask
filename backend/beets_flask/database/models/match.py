from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from beets_flask.database.models.pending import BeetsItemType
from beets_flask.importer.types import BeetsItem

from .base import Base

# --------------------------------- Distance --------------------------------- #


class Distance(Base):
    __tablename__ = "distances"

    track_info_id: Mapped[str | None] = mapped_column(ForeignKey("track_info.id"))
    parent_distance_id: Mapped[str | None] = mapped_column(ForeignKey("distances.id"))

    # FK columns auto-created from relationships
    track_info: Mapped[TrackInfo | None] = relationship()
    parent_distance: Mapped[Distance | None] = relationship(
        remote_side="Distance.id",
        back_populates="track_distances",
    )

    penalties: Mapped[list[Penalty]] = relationship(
        back_populates="distance",
        cascade="all, delete-orphan",
    )
    track_distances: Mapped[list[Distance]] = relationship(
        back_populates="parent_distance",
        cascade="all, delete-orphan",
    )

    raw_distance: Mapped[float] = mapped_column(default=0.0)
    max_distance: Mapped[float] = mapped_column(default=0.0)

    def __init__(
        self,
        raw_distance: float = 0.0,
        max_distance: float = 0.0,
        penalties: list[Penalty] | None = None,
        track_distances: list[Distance] | None = None,
        id: str | None = None,
    ):
        super().__init__(id)
        self.raw_distance = raw_distance
        self.max_distance = max_distance
        self.penalties = penalties or []
        self.track_distances = track_distances or []


class Penalty(Base):
    """Individual penalty entries."""

    __tablename__ = "penalties"

    key: Mapped[str] = mapped_column(index=True)
    value: Mapped[list[float]]
    distance_id: Mapped[int] = mapped_column(ForeignKey("distances.id"))

    # Derived
    distance: Mapped[Distance] = relationship(back_populates="penalties")

    def __init__(
        self,
        key: str,
        value: list[float],
        id: str | None = None,
    ):
        super().__init__(id)
        self.key = key
        self.value = value


# ----------------------------------- Info ----------------------------------- #


class TrackInfo(Base):
    __tablename__ = "track_info"

    album_id: Mapped[str | None] = mapped_column(ForeignKey("album_info.id"))
    album: Mapped[AlbumInfo] = relationship(back_populates="tracks")
    data: Mapped[dict[str, Any]] = mapped_column(JSON(), default=dict)

    def __init__(
        self,
        *,
        data: dict[str, Any] | None = None,
        id: str | None = None,
    ):
        super().__init__(id)
        self.data = data or {}


class AlbumInfo(Base):
    __tablename__ = "album_info"

    tracks: Mapped[list[TrackInfo]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON(), default=dict)

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        tracks: list[TrackInfo] | None = None,
        id: str | None = None,
    ):
        super().__init__(id)
        self.data = data or {}
        self.tracks = tracks or []


# ----------------------------------- Match ---------------------------------- #


class Match(Base):
    __tablename__ = "matches"

    # Needed for polymorphic
    id: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column()

    distance_id: Mapped[str] = mapped_column(ForeignKey("distances.id"))
    distance: Mapped[Distance] = relationship()

    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": "matches",
    }


class AlbumMatch(Match):
    __tablename__ = "matches_album"

    id: Mapped[str] = mapped_column(ForeignKey("matches.id"), primary_key=True)

    info_id: Mapped[str] = mapped_column(ForeignKey("album_info.id"))
    info: Mapped[AlbumInfo] = relationship()

    track_mappings: Mapped[list[AlbumMatchTrackMapping]] = relationship(
        back_populates="album_match",
        cascade="all, delete-orphan",
    )

    __mapper_args__ = {
        "polymorphic_identity": "album",
    }

    def __init__(
        self,
        info: AlbumInfo,
        distance: Distance,
        id: str | None = None,
    ) -> None:
        super().__init__(id)
        self.info = info
        self.distance = distance


class TrackMatch(Match):
    __tablename__ = "matches_track"

    id: Mapped[str] = mapped_column(ForeignKey("matches.id"), primary_key=True)

    info_id: Mapped[str] = mapped_column(ForeignKey("track_info.id"))
    info: Mapped[TrackInfo] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "track",
    }

    def __init__(
        self,
        info: TrackInfo,
        distance: Distance,
        id: str | None = None,
    ) -> None:
        self.info = info
        self.distance = distance
        super().__init__(id)


class AlbumMatchTrackMapping(Base):
    """Maps items to track_info for an album_match.

    Filter by album_match_id:
    - extra_tracks: track_info is not None and item_id is None
    - extra_items: track_info is None and item_id is not None
    - mapping: both are set
    """

    __tablename__ = "album_match_track_mappings"

    album_match_id: Mapped[str] = mapped_column(ForeignKey("matches_album.id"))
    track_info_id: Mapped[str | None] = mapped_column(ForeignKey("track_info.id"))
    item: Mapped[BeetsItem | None] = mapped_column(BeetsItemType())

    # ID of the beets library Item (not our model, just the raw ID)
    track_info: Mapped[TrackInfo | None] = relationship()
    album_match: Mapped[AlbumMatch] = relationship(back_populates="track_mappings")

    def __init__(
        self,
        item: BeetsItem | None = None,
        track_info: TrackInfo | None = None,
        id: str | None = None,
    ):
        self.track_info = track_info
        self.item = item
        super().__init__(id)
