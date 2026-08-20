"""Minimal state model for the beets_flask application.

Allows to resume a import at any time using our state dataclasses,
see importer/state.py for more information.

Why not just have State and StateInDb in the same class?
- ORM ideally wants full mirroring of whats in RAM in the DB. This is hard to ensure
  in our case, as we dont have full control over beets tasks etc.
- A lot of beets objects do not neatly translate to DB objects.
- Often we want states without having to think about a DB Session.
- Just a current motivation and choice, will revisit this later.
"""

from __future__ import annotations

import pickle
from collections.abc import Sequence
from pathlib import Path

from beets.importer import Action
from sqlalchemy import (
    ForeignKey,
    UniqueConstraint,
    case,
    select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    Mapped,
    Session,
    mapped_column,
    relationship,
)
from sqlalchemy.sql.elements import ColumnElement

from beets_flask.database.mapper.base import Context
from beets_flask.database.models.base import Base
from beets_flask.database.models.match import Distance, Match
from beets_flask.disk import Archive, Folder
from beets_flask.importer.progress import Progress
from beets_flask.importer.states import SessionState
from beets_flask.logger import log
from beets_flask.server.exceptions import SerializedException

from .pending import TaskItem


class FolderInDb(Base):
    """Represents a folder on disk, to keep track of changes.

    This folder does not necessarily have to exist on disk anymore. If the content
    changed, a new folder object (new hash) should be created.
    """

    __tablename__ = "folder"

    # Composite primary key
    full_path: Mapped[str] = mapped_column(index=True, primary_key=True)

    # checked -> yes | no or didnt check -> None
    is_album: Mapped[bool | None]

    def __init__(self, path: Path | str, hash: str, is_album: bool | None = None):
        """
        Create a FolderInDb object from a path.

        Convention:
        /home/user/foo/
        abs path with trailing slash.

        Parameters
        ----------
        path : Path
            The path to create the object from.
        """
        if isinstance(path, str):
            path = Path(path)
        self.full_path = str(path.resolve())
        self.hash = hash
        self.is_album = is_album

    @classmethod
    def from_live_folder(cls, folder: Folder | Archive) -> FolderInDb:
        """Create a FolderInDb object from a Folder object."""
        f_in_db = cls(
            path=folder.path,
            hash=folder.hash,
        )
        f_in_db.is_album = folder.is_album

        return f_in_db

    def to_live_folder(self) -> Folder:
        """Recreate the live Folder object from its stored version in the db."""
        return Folder(
            children=[],
            full_path=self.full_path,
            hash=self.hash,
            is_album=self.is_album or False,
        )

    def as_tuple(self) -> tuple[Path, str]:
        """Recreate the live Folder object from its stored version in the db."""
        return (
            self.path,
            self.hash,
        )

    @property
    def hash(self) -> str:
        """
        Convenience property to get the id.

        Note: Although the id is just the hash, when querying the db, you **must** use `FolderInDb.id == hash`. Sqlalchemy does not resolve properties.
        """
        return self.id

    @hash.setter
    def hash(self, value: str):
        self.id = value

    @property
    def path(self) -> Path:
        return Path(self.full_path)

    @classmethod
    def get_current_on_disk(cls, hash: str, path: Path | str) -> Folder | Archive:
        """
        Check that a folders hash is still the same, as you have previously determined.

        If changed, a new instance of FolderInDb is created and stored in the DB.

        Returns
        -------
        Folder: The live folder object on disk, with the potentially new (current) hash.
        """
        from beets_flask.database.setup import db_session_factory

        with db_session_factory() as db_session:
            if isinstance(path, str):
                path = Path(path)
            # Check if archive
            f_on_disk: Folder | Archive
            if path.is_dir():
                f_on_disk = Folder.from_path(path)
            else:
                f_on_disk = Archive.from_path(path)

            f_in_db = FolderInDb.get_by(FolderInDb.id == hash, session=db_session)
            if f_in_db is None:
                f_in_db = FolderInDb.from_live_folder(f_on_disk)
                db_session.merge(f_in_db)
                db_session.commit()

            if f_in_db.hash != f_on_disk.hash:
                log.debug(
                    f"Hash mismatch {path=} {f_in_db.hash=} {f_on_disk.hash=}"
                    + "This indicatest that the folder has changed."
                )
            return f_on_disk


class SessionStateInDb(Base):
    """Represents an import session.

    Normally a session has one task but in theory and edge cases
    we could have multiple tasks per session.

    Beets uses sessions for the back-and-forth dialog with the user,
    where one session may have multiple tasks.
    We wrap the beets session in our SessionState to better handle its progress.
    And our SessionState has a representation in our database, the SessionStateInDb.

    Example:
    ```
    # Create
    s_live_state = SessionState(Path("path"))
    session = PreviewSession(s_live_state)
    s_live_state = session.run_sync()
    s_db_state = SessionStateInDb.from_live_state(s_live_state)

    # Search
    select(SessionStateInDb).where(TaskStateInDb.id == "some path").first()
    s_db_state = SessionStateInDb.get_by(
    ```
    """

    __tablename__ = "session"

    tasks: Mapped[list[TaskStateInDb]] = relationship(
        back_populates="session",
        # all: All operations cascade i.e. session.merge!
        # delete-orphan: Automatic deletion of tasks if not referenced
        # by a session anymore
        # See also https://docs.sqlalchemy.org/en/20/orm/cascades.html#unitofwork-cascades
        cascade="all, delete-orphan",
    )

    folder: Mapped[FolderInDb] = relationship()
    folder_hash: Mapped[str] = mapped_column(ForeignKey("folder.id"))
    folder_revision: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        UniqueConstraint(
            "folder_hash", "folder_revision", name="uq_folder_hash_revision"
        ),
    )
    # We have folder revisions to allow multiple sessions for the same folder hash,
    # the purpose being that we want to keep old sessions around. E.g. to not loose
    # old data when regenerating previews.
    # but at the same time, we want a soft 1:1 mapping between folder hash and session.
    # Thus, revisions are needed: the session-hash link always uses the highest revision.

    # FIXME: This should be a getter for the which queries the tasks
    progress: Mapped[Progress]

    # If an session run fails we want to store the exception
    exc: Mapped[bytes | None]

    def __init__(
        self,
        folder: FolderInDb,
        id: str | None = None,
        tasks: list[TaskStateInDb] = [],
        progress: Progress = Progress.NOT_STARTED,
        exc: SerializedException | None = None,
    ):
        super().__init__(id)
        self.folder = folder
        self.tasks = tasks
        self.progress = progress
        self.exc = pickle.dumps(exc) if exc else None

    @property
    def folder_path(self) -> Path:
        return self.folder.path

    @classmethod
    def get_by_hash_and_path(
        cls,
        hash: str | None,
        path: Path | str | None,
        db_session: Session | None = None,
    ) -> SessionStateInDb | None:
        """
        Get a session by its hash and if this fails, try its path.

        If multiple matches, returns the most recent one.
        """
        from beets_flask.database import db_session_factory

        with db_session_factory(db_session) as db_session:
            item = None
            if hash is not None:
                query = (
                    select(cls)
                    .where(cls.folder_hash == hash)
                    # hash+revision combos have unique constraints
                    # and sessions always point to the latest / highest revision.
                    .order_by(cls.folder_revision.desc())
                )
                item = db_session.execute(query).scalars().first()
            if item is None and path is not None:
                # Try to get by path
                # paths do not have revisions, always use last updated session
                query = (
                    select(cls)
                    .join(cls.folder)
                    .where(FolderInDb.full_path == str(path))
                    .order_by(cls.updated_at.desc(), cls.folder_revision.desc())
                )
                item = db_session.execute(query).scalars().first()

            return item

    @classmethod
    def get_ids_by_hash_and_path(
        cls,
        hash_path_pairs: Sequence[tuple[str | None, Path | str | None]],
        db_session: Session | None = None,
    ) -> list[str | None]:
        """Resolve many (hash, path) pairs to session ids in two queries.

        Same lookup semantics as `get_by_hash_and_path`: by hash first
        (latest revision), then by path (most recently updated session).
        Returns a sequence of session ids in the same order as the input
        pairs; unresolved pairs map to None.
        """
        from beets_flask.database import db_session_factory

        with db_session_factory(db_session) as db_session:
            by_hash: dict[str, str] = {}
            hashes = [h for h, _ in hash_path_pairs if h]
            if hashes:
                query = (
                    select(cls.folder_hash, cls.id)
                    .where(cls.folder_hash.in_(hashes))
                    # highest revision first
                    .order_by(cls.folder_revision.desc())
                )
                for folder_hash, session_id in db_session.execute(query).all():
                    by_hash.setdefault(folder_hash, session_id)

            pending = [
                (i, str(p))
                for i, (h, p) in enumerate(hash_path_pairs)
                if (not h or h not in by_hash) and p
            ]
            by_path: dict[str, str] = {}
            if pending:
                query = (
                    select(FolderInDb.full_path, cls.id)
                    .join(cls.folder)
                    .where(FolderInDb.full_path.in_([p for _, p in pending]))
                    # most recently updated first
                    .order_by(cls.updated_at.desc(), cls.folder_revision.desc())
                )
                for full_path, session_id in db_session.execute(query).all():
                    by_path.setdefault(full_path, session_id)

            result: list[str | None] = [None] * len(hash_path_pairs)
            for i, (h, p) in enumerate(hash_path_pairs):
                item = by_hash.get(h) if h else None
                if item is None and p:
                    item = by_path.get(str(p))
                result[i] = item

            return result

    @property
    def exception(self) -> SerializedException | None:
        """Returns the exception of the session if it failed."""
        return pickle.loads(self.exc) if self.exc else None

    def to_live_state(self):
        """To live state.

        Outlook: We should remove this at some point once we refactor
        the live_state logic!
        """
        from beets_flask.database.mapper.states import SessionStateMapper

        mapper = SessionStateMapper()
        ctx = Context()
        return mapper.from_db(self, ctx)

    @classmethod
    def from_live_state(cls, live_state: SessionState):
        """From live state.

        Outlook: We should remove this at some point once we refactor
        the live_state logic!
        """
        from beets_flask.database.mapper.states import SessionStateMapper

        mapper = SessionStateMapper()
        ctx = Context()
        return mapper.to_db(live_state, ctx)


class TaskStateInDb(Base):
    """Represents an import task.

    More precisely, beets uses one task per album that goes through a bunch of stages.
    We wrap the beets task in our TaskState to better handle its progress.
    And this TaskState has a representation in our database, the TaskStateInDb.
    """

    __tablename__ = "task"

    # Relationships
    session_id: Mapped[str] = mapped_column(ForeignKey("session.id"))
    session: Mapped[SessionStateInDb] = relationship(
        back_populates="tasks",
        foreign_keys=[session_id],
    )

    candidates: Mapped[list[CandidateStateInDb]] = relationship(
        back_populates="task",
        foreign_keys="[CandidateStateInDb.task_id]",
        cascade="all, delete-orphan",
    )
    # Set at the end of the import session
    # use_alter=True to break circular FK with candidate.task_id
    chosen_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate.id", use_alter=True)
    )
    chosen_candidate: Mapped[CandidateStateInDb | None] = relationship(
        back_populates="task",
        foreign_keys=[chosen_candidate_id],
    )

    toppath: Mapped[bytes | None]

    # To reconstruct the beets task we need to store a few of its attributes
    paths: Mapped[bytes]
    old_paths: Mapped[bytes | None]
    # old_paths contain original file paths, but are only set when files are moved.
    # (which breaks some deep links that before were identical to paths, but no more!)
    pending_items: Mapped[list[TaskItem]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    choice_flag: Mapped[Action | None]

    # To allow for continue we need to store the current artist and album
    # TODO: REMOVE this is not needed!! We can look at the asis candidate for this!
    # E.g. frontend component to compare two candidates
    cur_artist: Mapped[str | None]
    cur_album: Mapped[str | None]

    progress: Mapped[Progress]

    def __init__(
        self,
        id: str | None = None,
        toppath: bytes | None = None,
        paths: list[bytes] = [],
        old_paths: list[bytes] | None = None,
        pending_items: list[TaskItem] = [],
        candidates: list[CandidateStateInDb] = [],
        chosen_candidate_id: str | None = None,
        progress: Progress = Progress.NOT_STARTED,
        choice_flag: Action | None = None,
        cur_artist: str | None = None,
        cur_album: str | None = None,
    ):
        super().__init__(id)
        self.toppath = toppath
        self.paths = pickle.dumps(paths)
        self.old_paths = pickle.dumps(old_paths) if old_paths else None

        self.pending_items = pending_items
        self.candidates = candidates
        self.chosen_candidate_id = chosen_candidate_id
        self.progress = progress
        self.choice_flag = choice_flag
        self.cur_artist = cur_artist
        self.cur_album = cur_album


class CandidateStateInDb(Base):
    """Represents a candidate (potential match) for an import task.

    Again: Beets-Candidate > CandidateState > CandidateStateInDb
    """

    __tablename__ = "candidate"

    task_id: Mapped[str] = mapped_column(ForeignKey("task.id"))
    task: Mapped[TaskStateInDb] = relationship(
        back_populates="candidates",
        foreign_keys=[task_id],
    )

    # Should deserialize to AlbumMatch|TrackMatch
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    match: Mapped[Match] = relationship()

    # Duplicate ids (if any) (beets_id)
    # TODO: We should recompute the duplicates on fetching data from the database
    duplicate_ids: Mapped[str]

    def __init__(
        self,
        match: Match,
        task: TaskStateInDb,
        duplicate_ids: list[str] = [],
        id: str | None = None,
    ):
        super().__init__(id)

        self.match = match
        self.task = task
        self.duplicate_ids = ";".join(map(str, duplicate_ids))

    @hybrid_property
    def normalized_distance(self) -> float:
        """Normalized beets distance of this candidate (0-1, lower is better).

        A max distance of zero (no penalties) counts as a perfect match.
        """
        distance = self.match.distance
        if distance.max_distance == 0:
            return 0.0
        return distance.raw_distance / distance.max_distance

    @normalized_distance.inplace.expression
    def _normalized_distance_expression(cls) -> ColumnElement[float]:
        """SQL counterpart of `normalized_distance`.

        Requires joins to `Match` and `Distance` in the query.
        """
        return case(
            (Distance.max_distance == 0, 0.0),
            else_=Distance.raw_distance / Distance.max_distance,
        )


__all__ = ["SessionStateInDb", "TaskStateInDb", "CandidateStateInDb"]
