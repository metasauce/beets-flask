import logging
from pathlib import Path

import pytest
from beets import autotag, importer

from beets_flask.database.models.states import SessionStateInDb
from beets_flask.importer.session import SessionState
from beets_flask.importer.stages import Progress
from tests.conftest import beets_lib_item
from tests.mixins.database import IsolatedDBMixin
from tests.unit.test_importer.test_states import get_album_match

log = logging.getLogger(__name__)


@pytest.fixture
def import_task(beets_lib):
    item = beets_lib_item(title="title", path="path")
    task = importer.ImportTask(paths=[b"a path"], toppath=b"top path", items=[item])

    track_info = autotag.TrackInfo(title="match title")
    album_match = get_album_match(
        [track_info], [item], album="match album", data_url="url"
    )

    task.candidates = [album_match]
    return task


class TestSessionStateInDb(IsolatedDBMixin):
    state: SessionState

    @pytest.fixture(autouse=True)
    def gen_session_state(self, import_task, tmpdir_factory):
        state = SessionState(Path(tmpdir_factory.mktemp("beets_flask_disk")))
        state.upsert_task(import_task)
        self.state = state

    def test_from_session_state(
        self,
    ):
        state_in_db = SessionStateInDb.from_live_state(self.state)

        assert state_in_db.folder.full_path == str(self.state.path)

        # Tasks generated
        assert len(state_in_db.tasks) == 1

        # Candidates generated
        assert len(state_in_db.tasks[0].candidates) == 1

    def test_merge_session(self, db_session_factory):
        # Insert state in db
        state_in_db = SessionStateInDb.from_live_state(self.state)
        with db_session_factory() as s:
            s.add(state_in_db)
            s.commit()

        # At a later point we create a new state and merge it
        state_in_db = SessionStateInDb.from_live_state(self.state)
        with db_session_factory() as s:
            state_in_db.folder.full_path = "new path"
            state_in_db.tasks[0].progress = Progress.IMPORT_COMPLETED
            state_in_db.tasks[0].candidates = []
            s.autoflush = True
            s.merge(state_in_db)
            s.commit()

        with db_session_factory() as s:
            # Check that new path is in db
            state_in_db = s.query(SessionStateInDb).filter_by(id=state_in_db.id).one()
            assert len(state_in_db.tasks) == 1

            # Check that the progress is updated
            assert state_in_db.tasks[0].progress == Progress.IMPORT_COMPLETED
            assert len(state_in_db.tasks[0].candidates) == 0
