from pathlib import Path

import pytest
from beets import autotag, importer
from quart.typing import TestClientProtocol as Client
from sqlalchemy import select
from sqlalchemy.orm import Session

from beets_flask.database.models.states import FolderInDb, SessionStateInDb
from beets_flask.importer.states import SessionState
from tests.conftest import beets_lib_item
from tests.mixins.database import IsolatedDBMixin
from tests.unit.test_importer.test_states import get_album_match


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


@pytest.fixture
async def session_in_db(db_session_factory, import_task, tmpdir_factory):
    # Add a session to the database
    sessions: list[SessionState] = []
    for i in range(3):
        session = SessionState(Path(tmpdir_factory.mktemp(f"session_{i}")))
        with db_session_factory() as db_session:
            session.upsert_task(import_task)
            session_in_db = SessionStateInDb.from_live_state(session)
            db_session.add(session_in_db)
            db_session.commit()
        sessions.append(session)

    yield sessions

    # Clean up the database
    with db_session_factory() as db_session:
        db_session.query(SessionStateInDb).delete()
        db_session.query(FolderInDb).delete()
        db_session.commit()


class TestSessionEndpoint(IsolatedDBMixin):
    """Test the end to end functionality of the model endpoints.

    We automatically generate the endpoints for the sqlalchemy models. Thus we also
    test each generated endpoint here in a relatively generic way.
    """

    @pytest.mark.asyncio
    async def test_get_all_empty(self, client: Client, db_session: Session):
        # If no database objects are present, the response should be an empty list.
        # And no pagination.

        # Clear library
        sessions = db_session.execute(select(SessionStateInDb)).scalars().all()
        for s in sessions:
            db_session.delete(s)
        db_session.commit()

        response = await client.get("/api_v1/session")
        assert response.status_code == 200
        data = await response.get_json()
        assert isinstance(data, dict)

        assert data["items"] == []
        assert data["next"] is None

    @pytest.mark.asyncio
    async def test_get_all(self, client: Client, session_in_db):
        response = await client.get("/api_v1/session")
        assert response.status_code == 200
        data = await response.get_json()
        assert isinstance(data, dict)

        assert len(data["items"]) == len(session_in_db)
        assert data["next"] is None

    @pytest.mark.asyncio
    async def test_get_all_pageination(self, client, session_in_db):
        response = await client.get("/api_v1/session?n_items=1")
        assert response.status_code == 200
        data = await response.get_json()
        assert isinstance(data, dict)

        assert len(data["items"]) == 1
        assert data["next"] is not None

        # Try to iter all pages
        items = data["items"]
        next = data["next"]
        while next:
            response = await client.get(next)
            assert response.status_code == 200
            data = await response.get_json()
            assert isinstance(data, dict)
            next = data["next"]
            items.extend(data["items"])

        assert len(items) == len(session_in_db)

    @pytest.mark.asyncio
    async def test_invalid_id(self, client: Client):
        response = await client.get("/api_v1/session/id/invalid_id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_param(self, client: Client):
        response = await client.get("/api_v1/session?cursor=invalid")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_by_id(self, client: Client, session_in_db):
        for s in session_in_db:
            response = await client.get(f"/api_v1/session/id/{s.id}")
            assert response.status_code == 200
            data = await response.get_json()
            assert isinstance(data, dict)
            assert data["id"] == s.id


@pytest.mark.skip("Not implemented")
class TestTaskEndpoint:
    pass


@pytest.mark.skip("Not implemented")
class TestCandidateEndpoint:
    pass
