from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

import pytest

from beets_flask.disk import Folder

from ..test_flows import SendStatusMockMixin

if TYPE_CHECKING:
    from pathlib import Path


class TestDeleteEndpoint(SendStatusMockMixin):
    tmp_path: Path

    @pytest.fixture(autouse=True)
    def create_folder(self, tmp_path):
        # Create some folders
        os.makedirs(tmp_path / "basic")
        os.makedirs(tmp_path / "complex")
        os.makedirs(tmp_path / "complex" / "nested")
        with open(tmp_path / "basic" / "file1.txt", "w") as f:
            f.write("Hello World")
        with open(tmp_path / "complex" / "file2.txt", "w") as f:
            f.write("Hello World 12")
        with open(tmp_path / "complex" / "nested" / "file3.txt", "w") as f:
            f.write("Hello World 123")

        self.tmp_path = tmp_path

        yield

        # Cleanup after the test
        shutil.rmtree(tmp_path / "basic", ignore_errors=True)
        shutil.rmtree(tmp_path / "test2", ignore_errors=True)

    async def test_basic_delete(self, client):
        # Assuming the hashes are already known
        f1 = Folder.from_path(self.tmp_path / "basic")

        response = await client.delete(
            "/api_v1/inbox/delete",
            json={
                "folder_paths": [f1.full_path],
                "folder_hashes": [f1.hash],
            },
        )
        data = await response.get_json()

        assert response.status_code == 200
        assert data["deleted"] == [f1.full_path]
        assert data["hashes"] == [f1.hash]

    @pytest.mark.parametrize(
        "reverse",
        [True, False],
    )
    async def test_complex_delete(self, client, reverse):
        # Assuming the hashes are already known
        f1 = Folder.from_path(self.tmp_path / "complex")
        f2 = Folder.from_path(self.tmp_path / "complex" / "nested")

        folder_paths = [f1.full_path, f2.full_path]
        folder_hashes = [f1.hash, f2.hash]

        if reverse:
            folder_paths.reverse()
            folder_hashes.reverse()

        response = await client.delete(
            "/api_v1/inbox/delete",
            json={"folder_paths": folder_paths, "folder_hashes": folder_hashes},
        )
        data = await response.get_json()

        assert response.status_code == 200
        assert data["deleted"]
        assert len(data["deleted"]) == 2
        for deleted in data["deleted"]:
            assert deleted in folder_paths
        for deleted_hash in data["hashes"]:
            assert deleted_hash in folder_hashes

    async def test_dedupe_delete(self, client):
        # Assuming the hashes are already known
        f1 = Folder.from_path(self.tmp_path / "basic")
        f2 = Folder.from_path(self.tmp_path / "complex")

        folder_paths = [f1.full_path, f2.full_path, f1.full_path]
        folder_hashes = [f1.hash, f2.hash, f1.hash]

        response = await client.delete(
            "/api_v1/inbox/delete",
            json={"folder_paths": folder_paths, "folder_hashes": folder_hashes},
        )
        data = await response.get_json()

        assert response.status_code == 200
        assert data["deleted"]
        assert len(data["deleted"]) == 2

    async def test_invalid_hash(self, client):
        # Assuming the hashes are already known
        f1 = Folder.from_path(self.tmp_path / "basic")

        response = await client.delete(
            "/api_v1/inbox/delete",
            json={
                "folder_paths": [f1.full_path],
                "folder_hashes": ["invalid_hash"],
            },
        )
        data = await response.get_json()

        assert response.status_code == 400
        assert data["type"] == "InvalidUsageError"
        assert (
            data["message"]
            == "Folder hash does not match the current folder hash! Please refresh your hashes before deleting!"
        )
