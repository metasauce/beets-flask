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

import io
import pickle
from pathlib import Path
from typing import Any

from beets.autotag import AlbumMatch
from beets.autotag.distance import Distance
from beets.importer import Action, ImportTask
from sqlalchemy import (
    ForeignKey,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    Session,
    mapped_column,
    relationship,
)

from beets_flask.database.models.base import Base
from beets_flask.disk import Archive, Folder
from beets_flask.importer.progress import Progress
from beets_flask.importer.states import (
    CandidateState,
    SerializedCandidateState,
    SerializedSessionState,
    SerializedTaskState,
    SessionState,
    TaskState,
)
from beets_flask.importer.types import BeetsAlbumMatch, BeetsItem, BeetsTrackMatch
from beets_flask.logger import log
from beets_flask.server.exceptions import SerializedException

from .pending import TaskPendingItem


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

    @classmethod
    def from_live_state(cls, state: SessionState) -> SessionStateInDb:
        """Create the DB representation of a live SessionState.."""

        session = cls(
            folder=FolderInDb(state.folder_path, state.folder_hash),
            id=state.id,
            tasks=[TaskStateInDb.from_live_state(ts) for ts in state.task_states],
            progress=state.progress.progress,
            exc=state.exc,
        )

        return session

    @property
    def folder_path(self) -> Path:
        return self.folder.path

    def to_live_state(self, new_folder=True) -> SessionState:
        """Recreate the live SessionState with underlying task from its stored version in the db.

        HACK: new_folder param is a bit hacky, as if we do not include the children if we
        are not recomputing the folder hash. Might lead to some issues down the line.
        """

        if new_folder:
            s_state = SessionState(self.folder.path)
        else:
            s_state = SessionState(self.folder.to_live_folder())

        if s_state.folder_hash != self.folder.hash:
            log.warning(
                f"Folder hash mismatch for {self.folder.path}. "
                f"Expected {self.folder.hash} but got {s_state.folder_hash}."
            )
        s_state.id = self.id
        s_state.created_at = self.created_at
        s_state.updated_at = self.updated_at
        s_state._task_states = [task.to_live_state(s_state) for task in self.tasks]
        s_state.exc = pickle.loads(self.exc) if self.exc else None
        return s_state

    def to_dict(self) -> SerializedSessionState:
        return self.to_live_state(False).serialize()

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

    @property
    def exception(self) -> SerializedException | None:
        """Returns the exception of the session if it failed."""
        return pickle.loads(self.exc) if self.exc else None


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
    pending_items: Mapped[list[TaskPendingItem]] = relationship(
        cascade="all, delete-orphan"
    )
    choice_flag: Mapped[Action | None]

    # To allow for continue we need to store the current artist and album
    # TODO: REMOVE this is not needed!! We can look at the asis candidate for this!
    # E.g. frontend component to compare two candidates
    cur_artist: Mapped[str | None]
    cur_album: Mapped[str | None]

    progress: Mapped[Progress]

    @property
    def items(self) -> list[BeetsItem]:
        return [row.item for row in self.pending_items]

    @items.setter
    def items(self, value: list[BeetsItem]):
        self.pending_items = [TaskPendingItem(item=v) for v in value]

    def __init__(
        self,
        id: str | None = None,
        toppath: bytes | None = None,
        paths: list[bytes] = [],
        old_paths: list[bytes] | None = None,
        items: list[BeetsItem] = [],
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

        self.items = items
        self.candidates = candidates
        self.chosen_candidate_id = chosen_candidate_id
        self.progress = progress
        self.choice_flag = choice_flag
        self.cur_artist = cur_artist
        self.cur_album = cur_album

    @classmethod
    def from_live_state(cls, state: TaskState) -> TaskStateInDb:
        """Create the DB representation of a live TaskState."""
        if hasattr(state.task, "old_paths"):
            old_paths = state.task.old_paths
        else:
            old_paths = None

        task = cls(
            id=state.id,
            toppath=str(state.toppath).encode("utf-8") if state.toppath else None,
            paths=state.task.paths,
            items=state.items,
            candidates=[
                CandidateStateInDb.from_live_state(c) for c in state.candidate_states
            ],
            chosen_candidate_id=state.chosen_candidate_state_id,
            progress=state.progress.progress,
            choice_flag=state.task.choice_flag,
            cur_artist=state.task.cur_artist,
            cur_album=state.task.cur_album,
            old_paths=old_paths,
        )
        return task

    def to_live_state(self, session_state: SessionState | None = None) -> TaskState:
        """Recreate the live TaskState with underlying task from its stored version in the db."""

        # We just assume it is a normal import task
        beets_task = ImportTask(
            toppath=self.toppath,
            paths=pickle.loads(self.paths),
            items=self.items,
        )
        beets_task.choice_flag = self.choice_flag
        beets_task.cur_artist = self.cur_artist
        beets_task.cur_album = self.cur_album
        old_paths: list[bytes] | None = (
            pickle.loads(self.old_paths) if self.old_paths else None
        )
        # TODO: Update type hints once beets is updated
        beets_task.old_paths = old_paths  # type: ignore

        live_state = TaskState(beets_task)
        live_state.id = self.id
        live_state.created_at = self.created_at
        live_state.updated_at = self.updated_at
        live_state.candidate_states = [
            c.to_live_state(live_state) for c in self.candidates
        ]
        live_state.chosen_candidate_state_id = self.chosen_candidate_id
        live_state.progress.progress = self.progress

        # Set candidate of beets_task
        live_state.task.candidates = [c.match for c in live_state.candidate_states]

        return live_state

    def to_dict(self) -> SerializedTaskState:
        return self.to_live_state().serialize()


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
    # ~4kb per match
    match: Mapped[bytes]

    # Duplicate ids (if any) (beets_id)
    duplicate_ids: Mapped[str]

    # association between tracks online and items on disk, from int to int
    mapping: Mapped[dict[int, int]]

    def __init__(
        self,
        match: BeetsAlbumMatch | BeetsTrackMatch,
        mapping: dict[int, int],
        duplicate_ids: list[str] = [],
        id: str | None = None,
    ):
        super().__init__(id)

        # Remove db from all items as it can't be pickled
        # FIXME: this should go into beets __getstate__ method
        # see https://github.com/beetbox/beets/pull/5641
        if isinstance(match, BeetsAlbumMatch):
            for item in match.mapping.keys():
                item._db = None
                item._Item__album = None
            for item in match.extra_items:
                item._db = None
                item._Item__album = None

        self.match = pickle.dumps(match)
        self.duplicate_ids = ";".join(map(str, duplicate_ids))
        self.mapping = mapping

    @classmethod
    def from_live_state(cls, state: CandidateState) -> CandidateStateInDb:
        """Create the DB representation of a live CandidateState."""
        return cls(
            id=state.id,
            match=state.match,
            duplicate_ids=state.duplicate_ids,
            mapping=state._mapping,
        )

    def to_live_state(self, task_state: TaskState | None) -> CandidateState:
        """Recreate the live CandidateState with underlying task from its stored version in the db."""
        if task_state is None:
            task_state = self.task.to_live_state()
        live_state = CandidateState(
            CustomUnpickler(io.BytesIO(self.match)).load(),
            task_state,
            mapping=self.mapping,
        )
        live_state.id = self.id
        live_state.created_at = self.created_at
        live_state.updated_at = self.updated_at
        live_state.duplicate_ids = (
            # edge case: "".split() gives ['']
            [] if len(self.duplicate_ids) == 0 else self.duplicate_ids.split(";")
        )
        return live_state

    def to_dict(self) -> SerializedCandidateState:
        return self.to_live_state(self.task.to_live_state()).serialize()


# Hotfix for match unpickler to resolve beets distance moved
# This is needed because various beets updates changed class implementations
# and we want to rebuild the newer versions of some beets classes from old pickles.
# TODO: We should fix this in general and not pickle beets objects
class CustomUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        """Override the find_class method to redirect Distance class references."""
        # Redirect Distance class from beets.autotag.hooks to beets.distance (2.4.0)
        if module == "beets.autotag.hooks" and name == "Distance":
            return Distance

        # For all other classes, use the default lookup mechanism
        return super().find_class(module, name)

    def load(self) -> Any:
        object = super().load()
        if isinstance(object, Distance):
            self.patch_distance(object)

        if isinstance(object, AlbumMatch):
            self.patch_distance(object.distance)

        return object

    def patch_distance(self, distance: Distance) -> Distance:
        # Rewrite "source" penalty to "data_source" penalty (2.5.0)
        if "source" in distance._penalties:
            log.debug(
                "Converting old distance.source to distance.data_source (changed in beets 2.5.0)"
            )
            distance._penalties["data_source"] = distance._penalties["source"]
            del distance._penalties["source"]

            # Potential infinite recursion, ah well
            for track, d in distance.tracks.items():
                self.patch_distance(d)
        return distance


__all__ = ["SessionStateInDb", "TaskStateInDb", "CandidateStateInDb"]
