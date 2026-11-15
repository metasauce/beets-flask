from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import beets_flask.dir_size as dir_size_module
from beets_flask.server.routes import inbox as inbox_routes
from beets_flask.server.routes.library import stats as library_stats

from ...mixins.database import IsolatedDBMixin

if TYPE_CHECKING:
    from pathlib import Path


class TestStatsRoutes(IsolatedDBMixin):
    async def test_library_stats(self, client, monkeypatch):
        async def size(path: Path) -> int:
            return 1234

        monkeypatch.setattr(library_stats, "dir_size", size)

        response = await client.get("/api_v1/library/stats")
        data = await response.get_json()

        assert response.status_code == 200
        assert data["size"] == 1234
        assert data["libraryPath"]

    async def test_library_stats_size_is_null_on_timeout(self, client, monkeypatch):
        async def slow_size(path: Path) -> int:
            await asyncio.sleep(5)
            return 1234

        monkeypatch.setattr(library_stats, "dir_size", slow_size)

        response = await client.get("/api_v1/library/stats")
        data = await response.get_json()

        assert response.status_code == 200
        assert data["size"] is None

    async def test_inbox_stats(self, client, monkeypatch):
        async def size(path: Path) -> int:
            return 1234

        monkeypatch.setattr(inbox_routes, "dir_size", size)

        response = await client.get("/api_v1/inbox/stats")
        data = await response.get_json()

        assert response.status_code == 200
        assert len(data) > 0
        for stats in data:
            assert stats["size"] == 1234
            assert stats["path"]
            assert isinstance(stats["nFiles"], int)

    async def test_inbox_stats_size_is_null_on_timeout(self, client, monkeypatch):
        async def slow_size(path: Path) -> int:
            await asyncio.sleep(5)
            return 1234

        monkeypatch.setattr(inbox_routes, "dir_size", slow_size)

        response = await client.get("/api_v1/inbox/stats")
        data = await response.get_json()

        assert response.status_code == 200
        for stats in data:
            assert stats["size"] is None

    async def test_size_arrives_on_a_later_request(self, client, monkeypatch):
        """What the frontend polling relies on: null first, number later."""
        walks = 0

        async def slow_du(path: Path) -> int:
            nonlocal walks
            walks += 1
            await asyncio.sleep(2.2)
            return 4242

        monkeypatch.setattr(dir_size_module, "_du_bytes", slow_du)

        response = await client.get("/api_v1/library/stats")
        assert (await response.get_json())["size"] is None

        await asyncio.sleep(0.3)
        response = await client.get("/api_v1/library/stats")
        assert (await response.get_json())["size"] == 4242
        assert walks == 1
