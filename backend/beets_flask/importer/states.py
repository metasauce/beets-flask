"""State classes represent the current state of an import session."""

from __future__ import annotations

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast
from uuid import uuid4 as uuid

import beets.ui.commands as uicommands
from beets import importer
from beets.ui import _open_library
from beets.util import bytestring_path, get_most_common_tags
from deprecated import deprecated

from beets_flask.config import get_config
from beets_flask.disk import Archive, Folder
from beets_flask.importer.progress import (
    Progress,
    ProgressState,
    SerializedProgressState,
)
from beets_flask.importer.types import DuplicateAction
from beets_flask.server.exceptions import SerializedException
from beets_flask.utility import capture_stdout_stderr

from .types import (
    AlbumInfo,
    BeetsAlbum,
    BeetsAlbumInfo,
    BeetsAlbumMatch,
    BeetsDistance,
    BeetsImportTask,
    BeetsItem,
    BeetsLibrary,
    BeetsTrackInfo,
    BeetsTrackMatch,
    ItemInfo,
    TrackInfo,
)


class BaseState(ABC):
    """Base class for all states.

    Some shared functionality, but mostly common attributes.
    """

    id: str
    created_at: datetime
    updated_at: datetime

    def __init__(self) -> None:
        self.id = str(uuid())
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def serialize(self) -> SerializedBaseState:
        """Serialize the state to a dictionary."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(init=False)
class SessionState(BaseState):
    """Highest level state of an import session.

    Contains task (selection) states for each task.
    """

    id: str
    _task_states: list[TaskState]
    folder_path: Path
    folder_hash: str

    # session-level buttons. continue from choose_match when not None
    user_response: Literal["abort"] | Literal["apply"] | None = None

    # If a session run fails we store the exc here
    # should be set to none whenever the session is started
    exc: SerializedException | None = None

    def __init__(self, folder: Folder | Archive | Path) -> None:
        super().__init__()

        # Alternate constructor is part of the SessionStateInDb class
        self._task_states = []
        if isinstance(folder, str):
            folder = Path(folder)
        if isinstance(folder, Path):
            if folder.is_dir():
                # If the path is a file, we assume it is an archive
                folder = Folder.from_path(folder)
            else:
                folder = Archive.from_path(folder)

        # Why not just a folder object as member?
        # -> We do not always want to compute the children (or save them to db)
        self.folder_path = folder.path
        self.folder_hash = folder.hash

    def __repr__(self) -> str:
        return (
            f"SessionState:\n"
            + f" * id={self.id}\n"
            + f" * folder_path={self.folder_path}\n"
            + f" * folder_hash={self.folder_hash}\n"
            + f" * task_states={[ts.id for ts in self.task_states]}\n"
            + f" * progress={self.progress}"
        )

    @property
    @deprecated("Use the folder attribute instead!")
    def path(self) -> Path:
        return self.folder_path

    @property
    def task_states(self):
        return self._task_states

    @property
    def task_state_ids(self):
        return [s.id for s in self.task_states]

    @property
    def tasks(self):
        return [s.task for s in self.task_states]

    @property
    def progress(self):
        """The session progress is the loweset progress of all tasks."""
        if len(self.task_states) == 0:
            return ProgressState(Progress.NOT_STARTED)

        return min([s.progress for s in self.task_states])

    def get_task_state_for_task(
        self,
        task: BeetsImportTask,
    ) -> TaskState | None:
        """Get the task state for a given task.

        Returns None if not found.
        """
        state: TaskState | None = None
        for s in self.task_states:
            if s.task == task:
                state = s
                break
        return state

    def get_task_state_for_task_raise(
        self,
        task: BeetsImportTask,
    ) -> TaskState:
        """Get the task state for a given task.

        Raises ValueError if not found.
        """
        state = self.get_task_state_for_task(task)
        if state is None:
            raise ValueError(f"Task {task} not found in session.")
        return state

    def get_task_state_by_id(self, id: str) -> TaskState | None:
        state: TaskState | None = None
        for s in self.task_states:
            if s.id == id:
                state = s
                break
        return state

    def upsert_task(
        self,
        task: BeetsImportTask,
    ) -> TaskState:
        """Upsert selection state.

        If it does not exist yet it is created or updated
        if entry exists.
        """
        state = self.get_task_state_for_task(task)

        if state is None:
            state = TaskState(task)
            self._task_states.append(state)

        return state

    def remove_task(self, task: BeetsImportTask) -> None:
        """Remove a task from the session state.

        If the task does not exist, nothing happens.
        """
        state = self.get_task_state_for_task(task)
        if state is not None:
            self._task_states.remove(state)

    def remove_task_by_id(self, id: str) -> None:
        """Remove a task from the session state by id.

        If the task does not exist, nothing happens.
        """
        state = self.get_task_state_by_id(id)
        if state is not None:
            self._task_states.remove(state)

    def serialize(self) -> SerializedSessionState:
        """JSON representation to match the frontend types."""

        r = SerializedSessionState(
            **super().serialize(),
            folder_path=str(self.folder_path),
            folder_hash=str(self.folder_hash),
            tasks=[s.serialize() for s in self.task_states],
            status=self.progress.serialize(),
        )

        if self.exc is not None:
            r["exc"] = self.exc

        return r


@dataclass(init=False)
class TaskState(BaseState):
    """State representation of a beets ImportTask.

    In the frontend, a selection of the available candidates in the task may be needed
    from the user. Exposes some (typed) attributes of the task (e.g. toppath, paths, items)
    Has a list of associated CandidateStates, that represent `matches` in beets.
    """

    progress: ProgressState
    task: BeetsImportTask
    candidate_states: list[CandidateState]
    chosen_candidate_state_id: str | None = None

    # the completed state blocks the choose_match function
    # of interactive sessions via our await_completion method
    completed: bool = False

    # User choices and user input in interactive Session
    # None if no choice has been made yet
    # (or the frontend has not marked the default selection)
    duplicate_action: DuplicateAction | None = None

    def __init__(
        self,
        task: BeetsImportTask,
    ) -> None:
        super().__init__()
        # we might run into inconsistencies here, if candidates of the task
        # change. but I do not know when or why they would.
        self.task = task
        self.candidate_states = [CandidateState(c, self) for c in self.task.candidates]
        self.progress = ProgressState()

    def __repr__(self) -> str:
        return (
            f"TaskState:\n"
            + f" * id={self.id}\n"
            + f" * candidate_states={[ts.id for ts in self.candidate_states]}\n"
            + f" * chosen_candidate_state_id={self.chosen_candidate_state_id}\n"
            + f" * progress={self.progress}\n"
            + f" * completed={self.completed}\n"
            + f" * toppath={self.toppath}\n"
        )

    @property
    def candidates(
        self,
    ) -> Sequence[BeetsAlbumMatch | BeetsTrackMatch]:
        """Task candidates, i.e. possible matches to choose from."""
        return self.task.candidates

    @property
    def asis_candidate_id(self) -> str:
        """Id of the asis candidate."""
        return "asis-" + str(self.id)

    @property
    def asis_candidate(self) -> CandidateState:
        """Get the asis candidate state."""
        return CandidateState.asis_candidate(self)

    def add_candidates(
        self,
        candidates: Sequence[BeetsAlbumMatch | BeetsTrackMatch],
        insert_at: int = 0,
    ) -> list[CandidateState]:
        """Add new candidates to the selection state."""
        if len(self.task.candidates) == 0 or len(self.candidate_states) == 0:
            insert_at = 0

        # task.candidates is a sequence and thus immutable
        _ = list(self.task.candidates)
        _[insert_at:insert_at] = candidates
        self.task.candidates = _

        new_states = [CandidateState(c, self) for c in candidates]
        self.candidate_states[insert_at:insert_at] = new_states
        return new_states

    def get_candidate_state_by_id(self, id: str) -> CandidateState | None:
        """Get candidate state by id."""
        for c in self.candidate_states + [self.asis_candidate]:
            if c.id == id:
                return c
        return None

    @property
    def chosen_candidate_state(self) -> CandidateState | None:
        if self.chosen_candidate_state_id is None:
            return None
        return self.get_candidate_state_by_id(self.chosen_candidate_state_id)

    @property
    def toppath(self) -> Path | None:
        """Highest-level (common) folder holding music files."""
        if self.task.toppath is not None and isinstance(self.task.toppath, bytes):
            return Path(self.task.toppath.decode("utf-8"))
        return None

    @property
    def paths(self) -> list[Path]:
        """Lowest-level folders holding music files."""
        return [Path(p.decode("utf-8")) for p in self.task.paths]

    @property
    def item_paths_before_import(self) -> list[Path]:
        """Explicit paths to all media files that would be imported."""
        if self.toppath is None:
            return []
        if self.toppath.is_file():
            return [self.toppath]

        items: list[bytes] = []
        for _, i in importer.tasks.albums_in_dir(bytestring_path(self.toppath)):
            # the generator returns a nested list of the outer diretories
            # and file paths. thus, extend and then cast
            items.extend(i)

        return [Path(i.decode("utf-8")) for i in items]

    @property
    def items(self) -> list[BeetsItem]:
        """Items (representing music files on disk) of the associated task."""
        return [item for item in self.task.items]

    @property
    def items_minimal(self) -> list[ItemInfo]:
        """Items of the associated task as MinimalItemAndTrackInfo."""
        return [ItemInfo.from_beets(i) for i in self.task.items]

    @property
    def best_candidate_state(self) -> CandidateState | None:
        """Returns the best candidate of this task (never asis)."""
        best = None
        for candidate in self.candidate_states:
            if best is None or candidate.distance < best.distance.distance:
                best = candidate
        return best

    @property
    def choice_flag(self) -> importer.tasks.Action | None:
        return self.task.choice_flag

    @choice_flag.setter
    def choice_flag(self, value: importer.tasks.Action | None):
        self.task.choice_flag = value

    @property
    def current_metadata(self) -> Metadata:
        """Current metadata of the task.

        This is the metadata of the music files on disk.
        (In a beets context, cur_artist and cur_album)
        """
        likelies, _ = get_most_common_tags(self.items)
        return Metadata(**{k: str(v) for k, v in likelies.items()})  # type: ignore[typeddict-item]

    # ---------------------------------------------------------------------------- #

    def serialize(self) -> SerializedTaskState:
        """JSON representation to match the frontend types."""
        return SerializedTaskState(
            **super().serialize(),
            items=self.items_minimal,
            candidates=[c.serialize() for c in self.candidate_states],
            asis_candidate=self.asis_candidate.serialize(),
            current_metadata=self.current_metadata,
            # TODO: maybe we can merge current_metadata (which is cur_artist/album in
            # old beets) into the asis_candidate
            chosen_candidate_id=self.chosen_candidate_state_id,
            duplicate_action=self.duplicate_action,
            completed=self.completed,
            toppath=str(self.toppath),
            paths=[str(p) for p in self.paths],
        )

    def set_progress(self, progress: ProgressState | Progress | str) -> None:
        """Set the progress of the task.

        If string is given it is set as the message of the current progress.
        """
        if isinstance(progress, ProgressState):
            self.progress = progress
        elif isinstance(progress, Progress):
            self.progress = ProgressState(progress)
        elif isinstance(progress, str):
            # just convenience for debugging should not be used in production
            self.progress.message = progress
        else:
            raise ValueError(f"Unknown progress type: {progress}")


@dataclass(init=False)
class CandidateState(BaseState):
    """
    State representation of a single candidate (match) for an import task.

    Can represent an album (self.type == "album") or a track (self.type == "track").
    Keeps a reference to the associated SelectionState, so we can access the beets task.
    Exposes some attributes of the task and match

    Note: currently only tested for album matches.
    """

    id: str
    duplicate_ids: list[str]  # Beets ids of duplicates in the library (album)
    match: BeetsAlbumMatch | BeetsTrackMatch
    # Reference upwards
    task_state: TaskState

    _mapping: dict[int, int]  # index mapping from items to tracks

    def __init__(
        self,
        match: BeetsAlbumMatch | BeetsTrackMatch,
        task_state: TaskState,
        mapping: dict[int, int] | None = None,
    ) -> None:
        super().__init__()
        self.match = match
        self.duplicate_ids = []  # checked and set by session
        self.task_state = task_state

        # current_mapping is dynamic and looks at the match to generate integer / index mapping
        # this can cause problems, when loading a previously imported candidate from the db
        # as, in this case, the mapping is wrong and _index_mapping will fail.
        # we take care of this by manually overwriting when constructing from the db.
        self._mapping = mapping or self.current_mapping

    def __repr__(self) -> str:
        return (
            f"CandidateState:\n"
            + f" * id={self.id}\n"
            + f" * match={self.match.info.album}\n"
            + f" * task_state_id={self.task_state.id}\n"
            + f" * distance={self.distance}\n"
            + f" * penalties={self.penalties}\n"
            + f" * {len(self.items)=}\n"
            + f" * {len(self.tracks)=}\n"
            + f" * mapping={self.mapping}\n"
        )

    @property
    def type(self) -> Literal["album", "track"]:
        if isinstance(self.match, BeetsAlbumMatch):
            return "album"
        elif isinstance(self.match, BeetsTrackMatch):
            return "track"
        else:
            raise ValueError("Unknown type")

    @property
    def diff_preview(self) -> str:
        """Diff preview of the match to the current meta data."""
        out, err, _ = capture_stdout_stderr(
            uicommands.show_change,
            self.task_state.task.cur_artist,
            self.task_state.task.cur_album,
            self.match,
        )
        res = out.lstrip("\n")
        if len(err) > 0:
            res += f"\n\nError: {err}"
        return res

    @classmethod
    def asis_candidate(cls, task_state: TaskState) -> CandidateState:
        """
        Alternate constructor for an asis import option.

        We mock the album match to display
        current meta data in the frontend.
        This is pretty much duct-tape.
        """
        items: list[BeetsItem] = task_state.task.items

        # FIXME: we do this lookup twice, once here and once in current_metadata
        if len(items) > 0:
            info, _ = get_most_common_tags(items)
        else:
            info = {}
        info["data_source"] = "asis"
        info["data_url"] = f"file://{task_state.toppath}"

        def _generate_kwargs(item):
            kwargs = {}
            # before import the keys are in _dirty,
            # after import in _fields
            for key in list(item._dirty) + list(item._fields):
                val = getattr(item, key)
                if val is not None and val != "":
                    kwargs[key] = val
            # tracks use index, items use track, and beets diff preview crashes without index
            kwargs["index"] = item.track or 0
            return kwargs

        tracks = [BeetsTrackInfo(**_generate_kwargs(i)) for i in items]

        match = BeetsAlbumMatch(
            distance=BeetsDistance(),
            info=BeetsAlbumInfo(
                tracks=tracks,
                **info,
            ),
            extra_items=[],
            extra_tracks=[],
            mapping={i: tracks[idx] for idx, i in enumerate(items)},
        )
        candidate = cls(match=match, task_state=task_state)
        candidate.id = task_state.asis_candidate_id
        # As the asis candidate state is not maintained we not to
        # recheck if it is a duplicate
        candidate.identify_duplicates()

        return candidate

    # --------------------- Helper to lift / unnset from match to -------------------- #
    @property
    def cur_artist(self) -> str:
        """Current artist, usually the meta data of the music files.

        Named to be consistent with beets.
        """
        return str(self.task_state.task.cur_artist)

    @property
    def cur_album(self) -> str:
        """Current album, usually the meta data of the music files.

        Named to be consistent with beets.
        """
        return str(self.task_state.task.cur_album)

    @property
    def artist(self) -> str | None:
        """Artist of the match."""
        return self.match.info.artist

    @property
    def album(self) -> str | None:
        """Album of the match."""
        return self.match.info.album

    @property
    def items(self) -> list[BeetsItem]:
        """In beets, items refers to the music files on disk.

        Tracks correspond to an online match, (or the library?)
        """
        return self.task_state.task.items

    @property
    def tracks(self) -> list[BeetsTrackInfo]:
        """Tracks of the match (usually tracks in online match)."""
        if isinstance(self.match, BeetsAlbumMatch):
            return self.match.info.tracks
        return [self.match.info]

    @property
    def distance(self) -> BeetsDistance:
        """Distance of the match to the current meta data.

        Metadata may be from the task i.e. album or track.
        """
        return self.match.distance

    @property
    def penalties(self) -> list[str]:
        penalties = list(self.match.distance.keys())

        # renaming for consistency!
        # Beets has a somewhat unintuitive naming:
        # "items" are things on disk
        # "tracks" are meta-data i.e. online.
        # but penalties:
        # "unmatched_tracks" have online not on disk
        # "missing_tracks" have on disk, not online

        # beets object | beets penalty    | beets_flask
        # -------------|------------------|------------
        # extra_items  | unmatched_tracks | extra_items
        # extra_tracks | missing_tracks   | extra_tracks

        penalties = [
            p.replace("unmatched_tracks", "extra_items").replace(
                "missing_tracks", "extra_tracks"
            )
            for p in penalties
        ]

        return list(penalties)

    @property
    def num_tracks(self) -> int:
        """Number of tracks in the match (usually tracks in online match)."""
        if isinstance(self.match, BeetsAlbumMatch):
            return len(self.match.info.tracks)
        return 1

    @property
    def num_items(self) -> int:
        """Number of items in the task (usually files on disk)."""
        return len(self.items)

    @property
    def url(self) -> str | None:
        """URL of the match."""
        if isinstance(self.match, BeetsAlbumMatch):
            try:
                return self.match.info.data_url
            except AttributeError:  # not set in the match
                return None

        return None

    @property
    def is_asis(self) -> bool:
        """Returns True if this is an "as is" candidate."""
        return self.id.startswith("asis-")

    @property
    def mapping(self) -> dict[int, int]:
        return self._mapping

    @property
    def current_mapping(self) -> dict[int, int]:
        """Get the current mapping from items to tracks, calculated from the match."""
        if isinstance(self.match, BeetsAlbumMatch):
            return _index_mapping(
                self.match.mapping,
                self.items,
                self.tracks,
            )

        raise ValueError("Current mapping only available for album matches.")

    # ------------------------------------ utility ----------------------------------- #

    def identify_duplicates(self, lib: BeetsLibrary | None = None) -> list[BeetsAlbum]:
        """Find duplicates.

        Copy of beets' `task.find_duplicates` but works on any candidates' match.

        # FIXME: Tracks are not checked for duplicates. Tbh noone cares about tracks anyways
        """
        if lib is None:
            lib = _open_library(get_config().beets_config)

        info = self.match.info.copy()
        info["albumartist"] = info["artist"]

        if info["artist"] is None:
            # As-is import with no artist. Skip check.
            return []

        # Construct a query to find duplicates with this metadata. We
        # use a temporary Album object to generate any computed fields.
        tmp_album = BeetsAlbum(lib, **info)
        keys: list[str] = cast(
            list[str],
            get_config().data.import_.duplicate_keys.album or [],
        )
        dup_query = tmp_album.duplicates_query(keys)

        # Re-Importing: Don't count albums with the same files as duplicates.
        task_paths = {i.path for i in self.task_state.task.items if i}

        duplicates: list[BeetsAlbum] = []
        for album in lib.albums(dup_query):
            # Check whether the album paths are all present in the task
            # i.e. album is being completely re-imported by the task,
            # in which case it is not a duplicate (will be replaced).
            album_paths = {i.path for i in album.items()}
            if not (album_paths <= task_paths):
                duplicates.append(album)

        # Write duplicates information!
        self.duplicate_ids = [d.id for d in duplicates]

        return duplicates

    @property
    def has_duplicates_in_library(self) -> bool:
        """Returns False, either if no duplicates found, or you have not checked yet.

        Call `identify_duplicates` first to ensure this works.
        """
        return len(self.duplicate_ids) > 0

    def serialize(self) -> SerializedCandidateState:
        """JSON representation to match the frontend types."""
        # we lift the match.info to reduce nesting in the frontend.
        info: TrackInfo | AlbumInfo
        tracks: list[TrackInfo]
        mapping: dict[int, int] = {}

        if isinstance(self.match.info, BeetsTrackInfo):
            # This hardly ever happens, we might support this more in the future
            info = TrackInfo.from_beets(self.match.info)
            tracks = [TrackInfo.from_beets(self.match.info)]
        elif isinstance(self.match.info, BeetsAlbumInfo):
            info = AlbumInfo.from_beets(self.match.info)

            # Map beets types to our types, allows serialization magic
            tracks = [TrackInfo.from_beets(track) for track in self.match.info.tracks]

            # mapping = _index_mapping(
            #     self.match.mapping,  # type: ignore
            #     self.items,
            #     self.tracks,
            # )
            mapping = self.mapping

        else:
            raise ValueError(f"Unknown type of matchinfo {type(self.match.info)}")

        res = SerializedCandidateState(
            **super().serialize(),
            penalties=self.penalties,
            duplicate_ids=self.duplicate_ids,
            type=self.type,
            distance=self.distance.distance,
            info=info,
            tracks=tracks,
            mapping=mapping,
        )

        return res


def _index_mapping(
    mapping: dict[BeetsItem, BeetsTrackInfo],
    items: list[BeetsItem],
    tracks: list[BeetsTrackInfo],
) -> dict[int, int]:
    """Helper to create an index mapping from items to tracks.

    the mapping of a beets albummatch uses objects, but we don not want
    to send them over redundantly. convert to an index mapping,
    where first index is in self.items, and second is in self.match.info.tracks

    This is used to serialize the mapping of a candidate state.
    """

    # log.debug(f"items: {[i.title for i in items]}")

    idxs = []
    tdxs = []
    for item, track in mapping.items():
        # log.debug(f"track: {track.index} {track.track_alt} {track.title}")
        # log.debug(f"item: {item.track} {item.title}")

        # compare items via paths, and tracks via full dicts
        # we used to compare via track_id, but this might be None.
        found_idx = found_tdx = None
        for idx, _ in enumerate(items):
            if item.path == items[idx].path:
                found_idx = idx
                break
        for tdx, _ in enumerate(tracks):
            if track == tracks[tdx]:
                found_tdx = tdx
                break
        idxs.append(found_idx)
        tdxs.append(found_tdx)

    if None in idxs or None in tdxs:
        raise ValueError(
            f"Index mapping failed: {idxs=} {tdxs=} {len(items)=} {len(tracks)=}"
        )

    # ignore type for mypy, we have checked that its not None!
    res: dict[int, int] = {idx: tdx for idx, tdx in zip(idxs, tdxs)}  # type: ignore[misc]
    # log.debug(f"Index mapping: {res}")

    return res


# ---------------------------- Serialization types --------------------------- #
# Used for getting typehints in the frontend. I.e. we generate the types from
# these typed dicts! See the generate_types.py script for more information.


class Metadata(TypedDict):
    """Returned from current_metadata().

    FIXME: I think this should not be defined here!
    """

    artist: str | None
    album: str | None
    albumartist: str | None
    year: str | None
    disctotal: str | None
    mb_albumid: str | None
    label: str | None
    barcode: str | None
    catalognum: str | None
    country: str | None
    media: str | None
    albumdisambig: str | None


class SerializedBaseState(TypedDict):
    """Serialized base state.

    This is used to serialize the base state to a dictionary.
    """

    id: str
    created_at: datetime
    updated_at: datetime


class SerializedSessionState(SerializedBaseState):
    folder_path: str
    folder_hash: str
    tasks: list[SerializedTaskState]
    status: SerializedProgressState

    exc: NotRequired[SerializedException | None]


class SerializedTaskState(SerializedBaseState):
    items: list[ItemInfo]
    current_metadata: Metadata

    # Fetched data
    candidates: list[SerializedCandidateState]
    asis_candidate: SerializedCandidateState

    duplicate_action: str | None
    chosen_candidate_id: str | None
    completed: bool
    toppath: str | None
    paths: list[str]


class SerializedCandidateState(SerializedBaseState):
    duplicate_ids: list[str]
    type: str

    penalties: list[str]
    distance: float

    info: TrackInfo | ItemInfo | AlbumInfo

    # Mapping from items to tracks index based
    mapping: dict[int, int]
    tracks: list[TrackInfo]


__all__ = [
    "SessionState",
    "TaskState",
    "CandidateState",
    "SerializedSessionState",
    "SerializedTaskState",
    "SerializedCandidateState",
]
