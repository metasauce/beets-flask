import pytest


class TestFileUploadRoute:
    @pytest.mark.parametrize(
        "filename, target_dir, expected_filename, expected_dir",
        [
            (
                "simple.txt",
                "upload_1",
                "simple.txt",
                "upload_1",
            ),
            (
                "file%20with%20spaces.txt",
                "upload_1/nested%20dir",
                "file with spaces.txt",
                "upload_1/nested dir",
            ),
            (
                "file.txt",
                "foo/bar/nested%2Fsubdir",
                "file.txt",
                "foo/bar/nested/subdir",
            ),
            (
                "file.txt",
                "foo/bar/nested%5Csubdir",
                "file.txt",
                "foo/bar/nested\\subdir",
            ),
        ],
    )
    async def test_successful_file_upload(
        self,
        client,
        tmp_path,
        monkeypatch,
        filename,
        target_dir,
        expected_filename,
        expected_dir,
    ):
        # Setup: create a valid inbox directory
        inbox_dir = tmp_path / "inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)

        # Monkey patch the inbox folders to include our temp inbox
        monkeypatch.setattr(
            "beets_flask.server.routes.file_upload.get_inbox_folders",
            lambda: [str(inbox_dir)],
        )

        # Perform the upload
        file_content = b"hello test file upload"
        headers = {
            "X-Filename": filename,
            "X-File-Target-Dir": str(inbox_dir / target_dir),
        }
        response = await client.post(
            "/api_v1/file_upload/",
            headers=headers,
            data=file_content,
        )

        # Check status codes
        data = await response.get_json()
        print(data)
        assert response.status_code == 200
        assert data["status"] == "ok"

        # Check file exists in target dir and content matches
        final_path = inbox_dir / expected_dir / expected_filename
        assert final_path.exists()
        with open(final_path, "rb") as f:
            assert f.read() == file_content

    @pytest.mark.parametrize(
        "headers",
        [
            {"X-File-Target-Dir": "/some/path"},
            {"X-Filename": "file.txt"},
        ],
    )
    async def test_missing_required_headers(self, client, headers):
        response = await client.post(
            "/api_v1/file_upload/",
            headers=headers,
            data=b"testdata",
        )
        data = await response.get_json()
        assert str(response.status_code).startswith("4")
        assert data["type"] == "InvalidUsageException"
        assert "Missing header" in data["message"]

    async def test_invalid_target_path(self, client, monkeypatch):
        # Patch get_inbox_folders to return a known inbox path
        monkeypatch.setattr(
            "beets_flask.server.routes.file_upload.get_inbox_folders",
            lambda: ["/valid/inbox"],
        )
        response = await client.post(
            "/api_v1/file_upload/",
            headers={
                "X-Filename": "file.txt",
                "X-File-Target-Dir": "/invalid/path",
            },
            data=b"testdata",
        )
        data = await response.get_json()
        assert str(response.status_code).startswith("4")
        assert data["type"] == "InvalidUsageException"
        assert "Invalid target path" in data["message"]

    async def test_invalid_filename_with_path_separators(self, client, monkeypatch):
        # Patch get_inbox_folders to return a known inbox path
        monkeypatch.setattr(
            "beets_flask.server.routes.file_upload.get_inbox_folders",
            lambda: ["/valid/inbox"],
        )
        response = await client.post(
            "/api_v1/file_upload/",
            headers={
                "X-Filename": "invalid/../file.txt",
                "X-File-Target-Dir": "/valid/inbox",
            },
            data=b"testdata",
        )
        data = await response.get_json()
        assert str(response.status_code).startswith("4")
        assert data["type"] == "InvalidUsageException"
        assert "Invalid filename" in data["message"]


class TestFileUploadValidationRoute:
    async def test_validate_endpoint_success(self, client, monkeypatch):
        """Test that the validate endpoint returns 200 for valid headers."""
        monkeypatch.setattr(
            "beets_flask.server.routes.file_upload.get_inbox_folders",
            lambda: ["/valid/inbox"],
        )
        response = await client.post(
            "/api_v1/file_upload/validate",
            headers={
                "X-Filename": "test.txt",
                "X-File-Target-Dir": "/valid/inbox/test_dir",
            },
            data=b"",
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

    async def test_validate_endpoint_missing_headers(self, client):
        """Test that the validate endpoint raises InvalidUsageException for missing headers."""
        response = await client.post(
            "/api_v1/file_upload/validate",
            headers={
                "X-Filename": "test.txt",
            },
            data=b"",
        )
        assert str(response.status_code).startswith("4")
        data = await response.get_json()
        assert data["type"] == "InvalidUsageException"
        assert "Missing header" in data["message"]

    async def test_validate_endpoint_invalid_filename(self, client, monkeypatch):
        """Test that the validate endpoint raises InvalidUsageException for invalid filenames."""
        # Patch get_inbox_folders to return a known inbox path
        monkeypatch.setattr(
            "beets_flask.server.routes.file_upload.get_inbox_folders",
            lambda: ["/valid/inbox"],
        )
        response = await client.post(
            "/api_v1/file_upload/validate",
            headers={
                "X-Filename": "invalid/../file.txt",
                "X-File-Target-Dir": "/valid/inbox",
            },
            data=b"",
        )
        assert str(response.status_code).startswith("4")
        data = await response.get_json()
        assert data["type"] == "InvalidUsageException"
        assert "Invalid filename" in data["message"]

    async def test_validate_endpoint_invalid_target_path(self, client, monkeypatch):
        """Test that the validate endpoint raises InvalidUsageException for invalid target paths."""
        # Patch get_inbox_folders to return a known inbox path
        monkeypatch.setattr(
            "beets_flask.server.routes.file_upload.get_inbox_folders",
            lambda: ["/valid/inbox"],
        )
        response = await client.post(
            "/api_v1/file_upload/validate",
            headers={
                "X-Filename": "file.txt",
                "X-File-Target-Dir": "/invalid/path",
            },
            data=b"",
        )
        assert str(response.status_code).startswith("4")
        data = await response.get_json()
        assert data["type"] == "InvalidUsageException"
        assert "Invalid target path" in data["message"]
