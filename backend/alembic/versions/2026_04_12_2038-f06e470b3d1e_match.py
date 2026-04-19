"""match

Revision ID: f06e470b3d1e
Revises: 925cf8989fbc
Create Date: 2026-04-12 20:38:28.263069

README:
Historically, candidate states included a pickled match item. This approach has proven
to be brittle and difficult to maintain. This migration implements a more refined
database schema for matches.
"""

from __future__ import annotations
from collections.abc import Sequence
import importlib.util
import io
from pathlib import Path
import pickle
from typing import Any, NamedTuple

import sqlalchemy as sa
from sqlalchemy.orm import Session
from beets_flask.logger import logging
from beets_flask.database.models import types
from alembic import op

# We depend on other migrations (no other easy way to import)
BASE_DIR = Path(__file__).resolve().parent
path = BASE_DIR / "2026_04_12_1847-925cf8989fbc_item_pending.py"
spec = importlib.util.spec_from_file_location("item_pending_migration", path)
if not spec or not spec.loader:
    raise ImportError
item_migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(item_migration)

# revision identifiers, used by Alembic.
revision: str = "f06e470b3d1e"
down_revision: str | Sequence[str] | None = "925cf8989fbc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    # core info table
    op.create_table(
        "album_info",
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_album_info_created_at", "album_info", ["created_at"])

    op.create_table(
        "track_info",
        sa.Column("album_id", sa.String(), sa.ForeignKey("album_info.id")),
        sa.Column("data", sa.JSON(), nullable=False),
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
    op.create_index("ix_distances_created_at", "distances", ["created_at"])

    # matches
    op.create_table(
        "matches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column(
            "distance_id", sa.String(), sa.ForeignKey("distances.id"), nullable=False
        ),
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
    op.create_index("ix_matches_created_at", "matches", ["created_at"])

    # mappings
    op.create_table(
        "album_match_track_mappings",
        sa.Column(
            "album_match_id",
            sa.String(),
            sa.ForeignKey("matches_album.id"),
            nullable=False,
        ),
        sa.Column("track_info_id", sa.String(), sa.ForeignKey("track_info.id")),
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id")),
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
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

    # Migrate candidate table
    with op.batch_alter_table("candidate") as batch_op:
        batch_op.add_column(sa.Column("match_id", sa.String(), nullable=True))

    migrate_data()

    with op.batch_alter_table("candidate") as batch_op:
        batch_op.drop_column("match")
        batch_op.alter_column("match_id", nullable=False)
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


def migrate_data():
    from beets_flask.database.mapper.match import (
        AlbumMatchMapper,
        TrackMatchMapper,
        Context,
    )

    conn = op.get_bind()
    session = Session(bind=conn)

    result = conn.execution_options(stream_results=True).execute(
        sa.text("SELECT id, match FROM candidate WHERE match IS NOT NULL")
    )
    total = conn.execute(
        sa.text("SELECT COUNT(*) FROM candidate WHERE match IS NOT NULL")
    ).scalar()
    for i, row in enumerate(result, start=1):
        if i % 100 == 0:
            log.info("Migrating matches %d / %d rows", i, total)

        candidate_id = row[0]
        match_blob = row[1]

        if not match_blob:
            continue

        try:
            beets_match = load_match(match_blob)

            # A bit of an anti patter here but easiest way out:
            # We depend on our mappers here and hope they do not change in the future
            db_match: Any
            if isinstance(beets_match, AlbumMatchStub):
                db_match = AlbumMatchMapper().from_beets(
                    beets_match,  # type: ignore[arg-type]
                    Context(),
                )

            else:
                db_match = TrackMatchMapper().from_beets(
                    beets_match,  # type: ignore[arg-type]
                    Context(),
                )

            session.add(db_match)
            session.flush()  # gets db_match.id

            conn.execute(
                sa.text("UPDATE candidate SET match_id = :match_id WHERE id = :id"),
                {"match_id": db_match.id, "id": candidate_id},
            )

        except Exception:
            log.exception("Failed to migrate candidate %s", candidate_id)
            raise

    log.info("Migrated %d / %d matches!", total, total)


def load_match(blob: bytes) -> AlbumMatchStub | TrackMatchStub:
    return MatchUnpickler(io.BytesIO(blob)).load()


# --------------------------- Mocked Beets Classes --------------------------- #


class AttributeDictStub:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def __getitem__(self, key):
        return self.__dict__[key]

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()


class DistanceStub:
    def __init__(self):
        self._penalties = {}
        self.tracks = {}
        self._raw_distance = 0.0  # Use private backing field
        self._max_distance = 0.0

    @property
    def raw_distance(self) -> float:
        return self._raw_distance

    @raw_distance.setter
    def raw_distance(self, value: float):
        self._raw_distance = value

    @property
    def max_distance(self) -> float:
        return self._max_distance

    @max_distance.setter
    def max_distance(self, value: float):
        self._max_distance = value

    def __getstate__(self):
        return {
            "_penalties": self._penalties,
            "tracks": self.tracks,
            "_raw_distance": self._raw_distance,
            "_max_distance": self._max_distance,
        }

    def __setstate__(self, state):
        self._penalties = state.get("_penalties", {})
        self.tracks = state.get("tracks", {})
        self._raw_distance = state.get("_raw_distance", 0.0)
        self._max_distance = state.get("_max_distance", 0.0)


class AlbumMatchStub(NamedTuple):
    distance: DistanceStub
    info: AttributeDictStub
    mapping: dict[Any, AttributeDictStub]  # Any = item_migration.ModelStub
    extra_items: list[Any]
    extra_tracks: list[AttributeDictStub]


class TrackMatchStub(NamedTuple):
    distance: DistanceStub
    info: AttributeDictStub


class MatchUnpickler(pickle.Unpickler):
    CLASS_MAP = {
        ("beets.dbcore.db", "LazyConvertDict"): item_migration.LazyConvertDictStub,
        ("beets.library", "Item"): item_migration.ModelStub,
        ("beets.library.models", "Item"): item_migration.ModelStub,
        ("beets.autotag.hooks", "AlbumMatch"): AlbumMatchStub,
        ("beets.autotag.hooks", "Distance"): DistanceStub,
        ("beets.autotag.hooks", "TrackInfo"): AttributeDictStub,
        ("beets.autotag.hooks", "AlbumInfo"): AttributeDictStub,
        ("beets.autotag.distance", "Distance"): DistanceStub,
        ("beetsplug.discogs", "IntermediateTrackInfo"): AttributeDictStub,
    }

    def find_class(self, module, name):
        """Override the find_class method to redirect Distance class references."""
        key = (module, name)
        if key not in self.CLASS_MAP:
            print(f"WARNING: Unknown class not in migration map: {module}.{name}")
            return dict  # Fallback for unknown classes
        return self.CLASS_MAP[key]

    def load(self) -> Any:
        object = super().load()
        if isinstance(object, DistanceStub):
            self._normalize(object)

        if isinstance(object, AlbumMatchStub):
            self._normalize(object.distance)

        return object

    def _normalize(self, obj):
        if isinstance(obj, DistanceStub):
            return self._normalize_distance(obj)
        return obj

    def _normalize_distance(self, distance: DistanceStub) -> DistanceStub:
        # Beets had a rename at some point which we need to handle here.
        if "source" in distance._penalties:
            distance._penalties["data_source"] = distance._penalties.pop("source")

        for _, child in distance.tracks.items():
            self._normalize_distance(child)

        return distance
