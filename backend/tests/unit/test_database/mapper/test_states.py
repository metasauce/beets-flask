"""Tests for the state mappers: SessionStateMapper, TaskStateMapper, CandidateStateMapper.

These tests verify bidirectional (roundtrip) conversion between live state objects
and their database model representations, following the same pattern as test_match.py.
"""

import pickle
from pathlib import Path

import pytest
from beets import importer
from beets.autotag.distance import Distance as BeetsDistance
from beets.autotag.hooks import AlbumMatch as BeetsAlbumMatch
from beets.autotag.hooks import TrackInfo as BeetsTrackInfo
from beets.autotag.hooks import TrackMatch as BeetsTrackMatch

from beets_flask.database.mapper.base import Context
from beets_flask.database.mapper.match import ItemMapper, MatchMapper
from beets_flask.database.mapper.states import (
    CandidateStateMapper,
    SessionStateMapper,
    TaskStateMapper,
)
from beets_flask.database.models.match import AlbumMatch
from beets_flask.database.models.states import (
    CandidateStateInDb,
    SessionStateInDb,
    TaskStateInDb,
)
from beets_flask.importer.states import CandidateState, SessionState, TaskState
from beets_flask.importer.types import BeetsItem
from tests.conftest import beets_lib_item
from tests.unit.test_database.mapper.test_match import create_beets_album_match

# ---------------------------------------------------------------------------
# Helper: build mapper instances without triggering infinite recursion
# ---------------------------------------------------------------------------
# The mappers have a circular __init__ dependency:
#   TaskStateMapper -> CandidateStateMapper -> TaskStateMapper -> ...
# We bypass __init__ via object.__new__ and wire up the sub-mappers manually,
# sharing instances to break the cycle.


def _build_candidate_mapper() -> CandidateStateMapper:
    """Build a CandidateStateMapper with a shared TaskStateMapper to avoid recursion."""
    cm = object.__new__(CandidateStateMapper)
    cm.match_mapper = MatchMapper()
    cm.task_mapper = _build_task_mapper(candidate_mapper=cm)
    return cm


def _build_task_mapper(
    candidate_mapper: CandidateStateMapper | None = None,
) -> TaskStateMapper:
    """Build a TaskStateMapper, optionally reusing an existing CandidateStateMapper."""
    tm = object.__new__(TaskStateMapper)
    tm.item_mapper = ItemMapper()
    if candidate_mapper is not None:
        tm.candidate_mapper = candidate_mapper
    else:
        tm.candidate_mapper = _build_candidate_mapper()
    return tm


def _build_session_mapper(want_to_serialize: bool = False) -> SessionStateMapper:
    """Build a SessionStateMapper that owns a fresh TaskStateMapper chain."""
    sm = object.__new__(SessionStateMapper)
    sm.task_mapper = _build_task_mapper()
    sm.want_to_serialize = want_to_serialize
    return sm


# ---------------------------------------------------------------------------
# Helper: create a minimal BeetsImportTask for testing
# ---------------------------------------------------------------------------


def _make_import_task(
    paths: list[bytes] | None = None,
    toppath: bytes | None = None,
    items: list[BeetsItem] | None = None,
) -> importer.ImportTask:
    """Create a minimal BeetsImportTask for mapper tests."""
    if paths is None:
        paths = [b"/fake/path/file1.mp3"]
    if toppath is None:
        toppath = b"/fake/path"
    if items is None:
        items = [beets_lib_item(title="test-item", path=str(paths[0], "utf-8"))]

    task = importer.ImportTask(paths=paths, toppath=toppath, items=items)
    return task


# ============================================================================
# Tests
# ============================================================================


class TestSessionStateMapper:
    """Tests for SessionState <-> SessionStateInDb roundtrip conversion."""

    def test_roundtrip_empty_session(self, tmp_path: Path):
        """Roundtrip a SessionState with no tasks."""
        mapper = _build_session_mapper()
        ctx = Context()

        # Create a live SessionState pointing at a real temp directory
        original = SessionState(tmp_path)

        # Convert to DB model
        model: SessionStateInDb = mapper.to_db(original, ctx)

        # Assert model structure
        assert isinstance(model, SessionStateInDb)
        assert model.folder.full_path == str(tmp_path.resolve())
        assert model.folder.hash == original.folder_hash
        assert len(model.tasks) == 0
        assert model.progress == original.progress.progress
        assert model.exc is None

        # Convert back to live object
        result: SessionState = mapper.from_db(model, ctx)

        # Assert roundtrip fidelity
        assert result.id == original.id
        assert result.folder_path == original.folder_path
        assert result.folder_hash == original.folder_hash
        assert len(result.task_states) == 0
        assert result.progress == original.progress

    def test_roundtrip_with_exception(self, tmp_path: Path):
        """Roundtrip a SessionState that carries a serialized exception."""
        from beets_flask.server.exceptions import SerializedException

        mapper = _build_session_mapper()
        ctx = Context()

        original = SessionState(tmp_path)
        original.exc = SerializedException(
            type="ValueError",
            message="something went wrong",
            trace="fake traceback",
        )

        # Convert to DB model
        model: SessionStateInDb = mapper.to_db(original, ctx)
        assert model.exc is not None

        # Convert back
        result: SessionState = mapper.from_db(model, ctx)
        assert result.exc is not None
        assert result.exc["type"] == "ValueError"
        assert result.exc["message"] == "something went wrong"

    def test_roundtrip_with_want_to_serialize(self, tmp_path: Path):
        """When want_to_serialize=True, from_db uses folder.to_live_folder()."""
        mapper = _build_session_mapper(want_to_serialize=True)
        ctx = Context()

        original = SessionState(tmp_path)

        model: SessionStateInDb = mapper.to_db(original, ctx)
        result: SessionState = mapper.from_db(model, ctx)

        # With want_to_serialize=True the folder is reconstructed via
        # folder.to_live_folder() which creates a Folder with children=[].
        # The key assertions: path and hash are preserved.
        assert result.folder_path == original.folder_path
        assert result.folder_hash == original.folder_hash


class TestTaskStateMapper:
    """Tests for TaskState <-> TaskStateInDb roundtrip conversion."""

    def test_roundtrip_minimal_task(self):
        """Roundtrip a TaskState with no candidates."""
        mapper = _build_task_mapper()
        ctx = Context()

        beets_task = _make_import_task()
        original = TaskState(beets_task)

        # Convert to DB model
        model: TaskStateInDb = mapper.to_db(original, ctx)

        # Assert model structure
        assert isinstance(model, TaskStateInDb)
        assert model.toppath == b"/fake/path"
        assert pickle.loads(model.paths) == [b"/fake/path/file1.mp3"]
        assert len(model.pending_items) == 1
        assert len(model.candidates) == 0
        assert model.progress == original.progress.progress
        assert model.choice_flag == beets_task.choice_flag
        assert model.cur_artist == beets_task.cur_artist
        assert model.cur_album == beets_task.cur_album
        assert model.old_paths is None

        # Convert back to live object
        result: TaskState = mapper.from_db(model, ctx)

        # Assert roundtrip fidelity
        assert result.id == original.id
        assert result.toppath == original.toppath
        assert result.paths == original.paths
        assert len(result.items) == 1
        assert len(result.candidate_states) == 0
        assert result.progress == original.progress
        assert result.task.choice_flag == beets_task.choice_flag

    def test_roundtrip_with_old_paths(self):
        """Roundtrip a TaskState whose underlying task has old_paths set."""
        mapper = _build_task_mapper()
        ctx = Context()

        beets_task = _make_import_task()
        # Simulate moved files: old_paths differ from paths
        beets_task.old_paths = [b"/old/path/file1.mp3"]

        original = TaskState(beets_task)

        # Convert to DB model
        model: TaskStateInDb = mapper.to_db(original, ctx)
        assert model.old_paths is not None
        assert pickle.loads(model.old_paths) == [b"/old/path/file1.mp3"]

        # Convert back
        result: TaskState = mapper.from_db(model, ctx)
        assert result.task.old_paths is not None
        assert result.task.old_paths == [b"/old/path/file1.mp3"]

    def test_task_items_roundtrip_preserves_fixed_and_flex_values(self):
        """Verify that BeetsItem fixed/flex attrs survive the roundtrip."""
        mapper = _build_task_mapper()
        ctx = Context()

        # Create an item with specific flex attributes
        item = beets_lib_item(title="roundtrip-title", artist="roundtrip-artist")
        item.genre = "roundtrip-genre"  # flex attr via __setattr__

        beets_task = _make_import_task(items=[item])
        original = TaskState(beets_task)

        model: TaskStateInDb = mapper.to_db(original, ctx)
        result: TaskState = mapper.from_db(model, ctx)

        assert len(result.items) == 1
        result_item = result.items[0]
        assert result_item.title == "roundtrip-title"
        assert result_item.artist == "roundtrip-artist"
        assert result_item.genre == "roundtrip-genre"

    def test_roundtrip_with_choice_flag_and_metadata(self):
        """Roundtrip a task that has choice_flag, cur_artist, cur_album set."""
        from beets.importer import Action

        mapper = _build_task_mapper()
        ctx = Context()

        beets_task = _make_import_task()
        beets_task.choice_flag = Action.ASIS
        beets_task.cur_artist = "Test Artist"
        beets_task.cur_album = "Test Album"

        original = TaskState(beets_task)

        model: TaskStateInDb = mapper.to_db(original, ctx)
        assert model.choice_flag == Action.ASIS
        assert model.cur_artist == "Test Artist"
        assert model.cur_album == "Test Album"

        result: TaskState = mapper.from_db(model, ctx)
        assert result.task.choice_flag == Action.ASIS
        assert result.task.cur_artist == "Test Artist"
        assert result.task.cur_album == "Test Album"


class TestCandidateStateMapper:
    """Tests for CandidateState <-> CandidateStateInDb roundtrip conversion."""

    @pytest.fixture
    def candidate_mapper(self) -> CandidateStateMapper:
        """Build a CandidateStateMapper wired to a shared TaskStateMapper."""
        return _build_candidate_mapper()

    @pytest.fixture
    def task_mapper(self) -> TaskStateMapper:
        """Build a standalone TaskStateMapper for use in tests."""
        return _build_task_mapper()

    def test_roundtrip_album_candidate_no_duplicates(
        self,
        candidate_mapper: CandidateStateMapper,
        task_mapper: TaskStateMapper,
    ):
        """Roundtrip an album-match CandidateState with no duplicates."""
        ctx = Context()

        # ---- build live objects ----
        item = beets_lib_item(title="disk-item")
        beets_task = _make_import_task(items=[item])
        task_state = TaskState(beets_task)

        beets_track = BeetsTrackInfo(title="candidate-track")
        album_match = create_beets_album_match(
            album_id="alb-1",
            album_name="Candidate Album",
            album_artist="Candidate Artist",
            tracks=[beets_track],
            distance_penalties={"artist": 0.1},
            mapping={item: beets_track},
        )

        original = CandidateState(match=album_match, task_state=task_state)

        # ---- to_db ----
        model: CandidateStateInDb = candidate_mapper.to_db(original, ctx)
        assert isinstance(model, CandidateStateInDb)
        assert model.duplicate_ids == ""
        assert isinstance(model.match, AlbumMatch)
        assert model.match.info.data["album"] == "Candidate Album"
        assert model.match.info.data["artist"] == "Candidate Artist"
        assert len(model.match.info.tracks) == 1
        assert model.match.info.tracks[0].data["title"] == "candidate-track"

        # ---- Wire up the task relationship on the model ----
        # In the real app SQLAlchemy sets this FK; in unit tests we do it
        # manually so that _from_db can roundtrip.
        task_model: TaskStateInDb = task_mapper.to_db(task_state, ctx)
        model.task = task_model

        # ---- from_db (use fresh context to avoid cache interference) ----
        ctx2 = Context()
        result: CandidateState = candidate_mapper.from_db(model, ctx2)

        assert result.id == original.id
        assert isinstance(result.match, BeetsAlbumMatch)
        assert result.match.info.album_id == "alb-1"
        assert result.match.info.album == "Candidate Album"
        assert result.match.info.artist == "Candidate Artist"
        assert len(result.match.info.tracks) == 1
        assert result.match.info.tracks[0].title == "candidate-track"
        assert result.duplicate_ids == []

    def test_roundtrip_with_duplicate_ids(
        self,
        candidate_mapper: CandidateStateMapper,
        task_mapper: TaskStateMapper,
    ):
        """Roundtrip a CandidateState that has duplicate IDs set."""
        ctx = Context()

        item = beets_lib_item(title="dup-item")
        beets_task = _make_import_task(items=[item])
        task_state = TaskState(beets_task)

        beets_track = BeetsTrackInfo(title="dup-track")
        album_match = create_beets_album_match(
            tracks=[beets_track],
            mapping={item: beets_track},
        )

        original = CandidateState(match=album_match, task_state=task_state)
        original.duplicate_ids = ["dup-1", "dup-2", "dup-3"]

        model: CandidateStateInDb = candidate_mapper.to_db(original, ctx)
        assert model.duplicate_ids == "dup-1;dup-2;dup-3"

        task_model: TaskStateInDb = task_mapper.to_db(task_state, ctx)
        model.task = task_model

        ctx2 = Context()
        result: CandidateState = candidate_mapper.from_db(model, ctx2)
        assert result.duplicate_ids == ["dup-1", "dup-2", "dup-3"]

    def test_roundtrip_track_match_candidate(
        self,
        candidate_mapper: CandidateStateMapper,
        task_mapper: TaskStateMapper,
    ):
        """Roundtrip a CandidateState wrapping a TrackMatch."""
        ctx = Context()

        beets_task = _make_import_task()
        task_state = TaskState(beets_task)

        # Build a TrackMatch
        track_distance = BeetsDistance()
        track_distance.add("artist", 0.1)
        beets_track = BeetsTrackInfo(
            title="Track Candidate",
            artist="Track Artist",
            length=200.0,
            index=1,
        )
        beets_item = beets_lib_item(title="Matched Item")
        track_match = BeetsTrackMatch(
            distance=track_distance,
            info=beets_track,
            item=beets_item,
        )

        original = CandidateState(match=track_match, task_state=task_state)

        model: CandidateStateInDb = candidate_mapper.to_db(original, ctx)
        from beets_flask.database.models.match import TrackMatch

        assert isinstance(model.match, TrackMatch)
        assert model.match.info.data["title"] == "Track Candidate"
        assert model.match.info.data["artist"] == "Track Artist"

        task_model: TaskStateInDb = task_mapper.to_db(task_state, ctx)
        model.task = task_model

        ctx2 = Context()
        result: CandidateState = candidate_mapper.from_db(model, ctx2)
        assert isinstance(result.match, BeetsTrackMatch)
        assert result.match.info.title == "Track Candidate"
        assert result.match.info.artist == "Track Artist"
        assert result.match.distance.raw_distance == track_distance.raw_distance
        assert result.match.item.title == "Matched Item"

    def test_empty_duplicate_ids_edge_case(
        self,
        candidate_mapper: CandidateStateMapper,
        task_mapper: TaskStateMapper,
    ):
        """Edge case: empty string in duplicate_ids should become [] not ['']."""
        ctx = Context()

        item = beets_lib_item(title="edge-item")
        beets_task = _make_import_task(items=[item])
        task_state = TaskState(beets_task)

        beets_track = BeetsTrackInfo(title="edge-track")
        album_match = create_beets_album_match(
            tracks=[beets_track], mapping={item: beets_track}
        )

        original = CandidateState(match=album_match, task_state=task_state)
        original.duplicate_ids = []

        model: CandidateStateInDb = candidate_mapper.to_db(original, ctx)
        assert model.duplicate_ids == ""

        task_model: TaskStateInDb = task_mapper.to_db(task_state, ctx)
        model.task = task_model

        ctx2 = Context()
        result: CandidateState = candidate_mapper.from_db(model, ctx2)
        assert result.duplicate_ids == []


class TestTaskStateWithCandidatesIntegration:
    """Integration-style tests: roundtrip a TaskState that contains candidates."""

    def test_roundtrip_task_with_candidates(self):
        """Full roundtrip: TaskState with candidates -> TaskStateInDb -> TaskState."""
        # Build shared mappers (avoiding recursion)
        task_mapper = _build_task_mapper()
        ctx = Context()

        # ---- build live TaskState with candidates ----
        item = beets_lib_item(title="integration-item")
        beets_task = _make_import_task(items=[item])
        beets_task.choice_flag = importer.Action.ASIS
        task_state = TaskState(beets_task)

        beets_track = BeetsTrackInfo(title="integration-track")
        album_match = create_beets_album_match(
            album_id="int-1",
            tracks=[beets_track],
            mapping={item: beets_track},
            distance_penalties={"source": 0.5},
        )
        # Simulate beets setting candidates on the task
        beets_task.candidates = [album_match]
        task_state.candidate_states = [CandidateState(album_match, task_state)]

        # ---- to_db ----
        model: TaskStateInDb = task_mapper.to_db(task_state, ctx)
        assert len(model.candidates) == 1
        assert model.candidates[0].match.info.data["album_id"] == "int-1"

        # Wire up reverse relationships on the candidate models
        for c_model in model.candidates:
            c_model.task = model

        # ---- from_db (fresh context) ----
        ctx2 = Context()
        result: TaskState = task_mapper.from_db(model, ctx2)

        assert len(result.candidate_states) == 1
        cs = result.candidate_states[0]
        assert isinstance(cs.match, BeetsAlbumMatch)
        assert cs.match.info.album_id == "int-1"
        assert cs.match.info.album == "Test Album"  # default from factory
        # The match info tracks are roundtripped
        assert len(cs.match.info.tracks) == 1
        assert cs.match.info.tracks[0].title == "integration-track"
        # The task-level attributes are preserved
        assert result.task.choice_flag == importer.Action.ASIS
        assert len(result.items) == 1
        assert result.items[0].title == "integration-item"
