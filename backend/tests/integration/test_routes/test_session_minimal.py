"""Integration tests for the custom `/api_v1/session/minimal` endpoint."""

from pathlib import Path
from typing import TypedDict

import pytest
from quart import Response
from quart.typing import TestClientProtocol as Client
from sqlalchemy.orm import Session

from beets_flask.database.models.match import AlbumInfo, AlbumMatch, Distance
from beets_flask.database.models.states import (
    CandidateStateInDb,
    FolderInDb,
    SessionStateInDb,
    TaskStateInDb,
)
from tests.mixins.database import IsolatedDBMixin


class Candidate(TypedDict):
    raw_distance: float
    max_distance: float
    duplicate_ids: list[str]
    data_source: str


def make_session(
    db_session: Session,
    folder: Path,
    *,
    folder_hash: str,
    candidates: list[Candidate],
) -> SessionStateInDb:
    task = TaskStateInDb(paths=[b"a path"], toppath=b"top path")
    session = SessionStateInDb(
        folder=FolderInDb(path=folder, hash=folder_hash),
        tasks=[task],
    )

    task.candidates = [
        CandidateStateInDb(
            match=AlbumMatch(
                info=AlbumInfo(data={"data_source": candidate["data_source"]}),
                distance=Distance(
                    raw_distance=candidate["raw_distance"],
                    max_distance=candidate["max_distance"],
                ),
            ),
            task=task,
            duplicate_ids=candidate["duplicate_ids"],
        )
        for candidate in candidates
    ]

    db_session.add(session)
    db_session.commit()
    return session


async def get_minimal(
    client: Client,
    *,
    folder_hash: str,
    folder_path: str,
) -> Response:
    return await client.get(
        "/api_v1/session/minimal",
        query_string={
            "folder_hash": folder_hash,
            "folder_path": folder_path,
        },
    )


class TestSessionMinimalEndpoint(IsolatedDBMixin):
    async def test_missing_folder_hash_returns_400(self, client: Client):
        response = await client.get("/api_v1/session/minimal")

        assert response.status_code == 400
        assert "at least one folder hash" in (await response.get_json())["message"]

    async def test_unknown_folder_returns_empty_response(self, client: Client):
        response = await get_minimal(
            client,
            folder_hash="unknown-hash",
            folder_path="/does/not/exist",
        )

        assert response.status_code == 200
        assert await response.get_json() == {}

    async def test_returns_best_candidate_for_session(
        self,
        client: Client,
        db_session: Session,
        tmp_path: Path,
    ):
        folder = tmp_path / "folder_a"
        session = make_session(
            db_session,
            folder,
            folder_hash="hash-a",
            candidates=[
                {
                    "raw_distance": 9.0,
                    "max_distance": 10.0,
                    "duplicate_ids": ["11", "22"],
                    "data_source": "musicbrainz",
                },
                {
                    "raw_distance": 1.0,
                    "max_distance": 10.0,
                    "duplicate_ids": ["33"],
                    "data_source": "spotify",
                },
            ],
        )

        response = await get_minimal(
            client,
            folder_hash="hash-a",
            folder_path=str(folder),
        )

        assert response.status_code == 200
        assert await response.get_json() == {
            "hash-a": {
                "session_id": session.id,
                "folder_hash": "hash-a",
                "best_candidate": {
                    "duplicates": [33],
                    "distance": pytest.approx(0.1),
                    "data_source": "spotify",
                },
            }
        }

    async def test_resolves_by_path_when_hash_changed(
        self,
        client: Client,
        db_session: Session,
        tmp_path: Path,
    ):
        folder = tmp_path / "folder_c"
        session = make_session(
            db_session,
            folder,
            folder_hash="old-hash",
            candidates=[
                {
                    "raw_distance": 1.0,
                    "max_distance": 10.0,
                    "duplicate_ids": ["5"],
                    "data_source": "spotify",
                },
            ],
        )

        response = await get_minimal(
            client,
            folder_hash="new-hash",
            folder_path=str(folder),
        )

        assert response.status_code == 200
        entry = (await response.get_json())["new-hash"]

        assert entry["session_id"] == session.id
        assert entry["folder_hash"] == "old-hash"
