import logging
from abc import ABC
from pathlib import Path

import pytest
from beets import autotag, importer

from beets_flask.importer.states import (
    CandidateState,
    Progress,
    SessionState,
    TaskState,
)
from beets_flask.importer.types import BeetsAlbumMatch, BeetsTrackInfo
from beets_flask.server.app import Encoder
from tests.conftest import beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin, IsolatedDBMixin

log = logging.getLogger(__name__)


def get_album_match(tracks: list[BeetsTrackInfo], items, **info):
    match = BeetsAlbumMatch(
        distance=autotag.Distance(),
        info=autotag.AlbumInfo(
            tracks=tracks,
            **info,
        ),
        extra_items=[],
        extra_tracks=[],
        mapping={i: tracks[idx] for idx, i in enumerate(items)},
    )
    return match


class StateTest(IsolatedBeetsLibraryMixin, IsolatedDBMixin, ABC):
    """Base class for tests that require a beets library."""

    @property
    def import_task(self):
        item = beets_lib_item(title="title", path="path")
        task = importer.ImportTask(paths=[b"a path"], toppath=b"top path", items=[item])

        track_info = autotag.TrackInfo(title="match title")
        album_match = get_album_match(
            [track_info], [item], album="match album", data_url="url"
        )

        task.candidates = [album_match]
        return task


class TestTaskState(StateTest):
    task: importer.ImportTask
    task_state: TaskState

    @pytest.fixture(autouse=True)
    def gen_task_state(self):
        self.task = self.import_task
        self.task_state = TaskState(self.task)

    def test_properties(self):
        task_state = self.task_state
        assert task_state.id is not None
        assert task_state.toppath == Path("top path")
        assert task_state.paths == [Path("a path")]
        assert task_state.items == [self.task.items[0]]
        assert task_state.progress == Progress.NOT_STARTED

        assert len(task_state.candidate_states) == len(self.task.candidates or [])

    def test_best_candidate(self):
        task_state = self.task_state
        assert task_state.best_candidate_state is not None
        assert self.task.candidates is not None
        assert task_state.best_candidate_state.match is self.task.candidates[0]

        self.task.candidates = []
        task_state = TaskState(self.task)
        # Should be none if no candidates (asis is not counted!)
        assert task_state.best_candidate_state is None

    def test_serialize(self):
        task_state = self.task_state
        serialized = task_state.serialize()
        assert isinstance(serialized, dict)
        assert serialized["id"] == task_state.id
        assert serialized["toppath"] == str(task_state.toppath)
        assert serialized["paths"] == [str(p) for p in task_state.paths]

        # Can be serialized with json.dumps and Encoder
        import json

        json.dumps(serialized, cls=Encoder)


class TestCandidateState(StateTest):
    task: importer.ImportTask
    task_state: TaskState
    candidates: list[CandidateState]

    @pytest.fixture(autouse=True)
    def gen_candidate_state(self):
        import_task = self.import_task
        task_state = TaskState(import_task)
        candidate_states = task_state.candidate_states

        assert len(candidate_states) == 1  # One from import_task
        self.candidates = candidate_states
        self.task = import_task
        self.task_state = task_state

    def test_properties(self):
        candidate = self.candidates[0]
        task = self.task

        assert isinstance(candidate, CandidateState)
        assert candidate.id is not None
        assert task.candidates is not None
        assert candidate.match == task.candidates[0]
        assert candidate.task_state == self.task_state
        assert candidate.type == "album"
        assert candidate.cur_artist == str(task.cur_artist)
        assert candidate.cur_album == str(task.cur_album)
        assert candidate.items == task.items
        assert candidate.tracks == candidate.match.info.tracks
        assert candidate.distance == candidate.match.distance
        assert candidate.num_tracks == len(candidate.match.info.tracks)
        assert candidate.num_items == len(candidate.items)
        assert candidate.url == task.candidates[0].info.data_url
        assert candidate.url == "url"

    def test_asis_candidate(self):
        # Test asis candidate (last in list)
        asis_candidate = self.task_state.asis_candidate
        assert self.task_state.asis_candidate_id == asis_candidate.id
        assert asis_candidate.id.startswith("asis")
        assert asis_candidate.type == "album"

    def test_diff_preview(self):
        candidate = self.candidates[0]
        diff_preview = candidate.diff_preview
        assert isinstance(diff_preview, str)
        assert "match album" in diff_preview

    def test_identify_duplicates(
        self,
    ):
        candidate = self.candidates[0]
        duplicates = candidate.identify_duplicates(self.beets_lib)
        assert isinstance(duplicates, list)
        assert len(duplicates) == 0
        assert candidate.has_duplicates_in_library is False

    def test_serialize(self):
        candidate = self.candidates[0]
        serialized = candidate.serialize()
        assert isinstance(serialized, dict)
        assert serialized["id"] == candidate.id
        assert serialized["penalties"] == candidate.penalties
        assert serialized["type"] == candidate.type
        assert serialized["distance"] == candidate.distance.distance

        # Can be serialized with json.dumps and Encoder
        import json

        json.dumps(serialized, cls=Encoder)


class TestSessionState(StateTest):
    task: importer.ImportTask
    session_state: SessionState

    @pytest.fixture(autouse=True)
    def gen_session_state(self, tmpdir_factory: pytest.TempdirFactory):
        self.session_state = SessionState(
            Path(tmpdir_factory.mktemp("beets_flask_disk"))
        )
        self.task = self.import_task
        self.session_state.upsert_task(self.task)

    def test_multiple_upserts(self):
        import_task = self.task
        session_state = self.session_state
        session_state.upsert_task(import_task)
        session_state.upsert_task(import_task)
        assert len(session_state.task_states) == 1

    def test_progress(self):
        session_state = self.session_state

        assert session_state.progress == Progress.NOT_STARTED

        for task in session_state.task_states:
            assert task.progress == Progress.NOT_STARTED
            task.set_progress(Progress.IMPORTING)

        # Should be minimal progress of all tasks i.e. IMPORTING
        assert session_state.progress == Progress.IMPORTING

        # Should return notstarted if no tasks
        session_state._task_states = []
        assert session_state.progress == Progress.NOT_STARTED

    def test_get_task(self):
        import_task = self.task
        session_state = self.session_state
        task_state = session_state.get_task_state_for_task(import_task)
        assert task_state is not None
        assert task_state.task is import_task

        # By id
        task_state = session_state.get_task_state_by_id(task_state.id)
        assert task_state is not None
        assert task_state.task is import_task

    def test_serialize(self):
        session_state = self.session_state
        serialized = session_state.serialize()
        assert isinstance(serialized, dict)
        assert serialized["id"] == session_state.id

        tasks_loaded = serialized["tasks"]
        tasks_current = [t.serialize() for t in session_state.task_states]
        assert len(tasks_loaded) == len(tasks_current)

        # the asis candidate sets the date freshly every time.
        for t_l, t_c in zip(tasks_loaded, tasks_current):
            t_c["asis_candidate"].pop("created_at")  # type: ignore[misc]
            t_c["asis_candidate"].pop("updated_at")  # type: ignore[misc]
            t_l["asis_candidate"].pop("created_at")  # type: ignore[misc]
            t_l["asis_candidate"].pop("updated_at")  # type: ignore[misc]
        assert tasks_loaded == tasks_current

        assert serialized["status"]["message"] is None
        assert serialized["status"]["progress"] == Progress.NOT_STARTED
        assert serialized["status"]["plugin_name"] == None

        # Can be serialized with json.dumps and Encoder
        import json

        json.dumps(serialized, cls=Encoder)
