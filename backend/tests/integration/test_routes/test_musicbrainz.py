import shutil
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from beets_flask.config import get_config
from beets_flask.config.beets_config import refresh_config
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

MBID_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BARCODE = "0723540055629"


class TestMusicbrainzEndpoint(IsolatedBeetsLibraryMixin):
    """Test class for the MusicBrainz preparation endpoints.

    Verifies that albums in the beets library can be prepared for the
    MusicBrainz release editor via the API.
    """

    _album_id: int | None = None

    @pytest.fixture(autouse=True)
    def album(self):  # type: ignore
        """Fixture to add an album to the beets library before running tests."""
        if self._album_id is not None:
            return

        a = beets_lib_album(
            album="The Album",
            albumartist="The Artist",
            year=2017,
            label="Some Label",
            barcode="0723540055629",
        )
        self.beets_lib.add(a)
        self.beets_lib.add(
            beets_lib_item(
                album_id=a.id,
                title="Track 1",
                artist="The Artist",
                track=1,
                disc=1,
                isrc="QZ5AB1840341",
                length=231.0,
                media="Digital Media",
            )
        )
        self.beets_lib.add(
            beets_lib_item(
                album_id=a.id,
                title="Track 2",
                artist="The Artist",
                track=2,
                disc=1,
                length=198.0,
                media="Digital Media",
            )
        )
        self._album_id = a.id

    async def test_status(self, client):
        """Test the GET request to check if the assistant is available."""
        response = await client.get("/api_v1/musicbrainz/status")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        assert data["enabled"] is True
        assert data["editor_url"].startswith("https://")

    async def test_prepare(self, client, monkeypatch):
        """Test the POST request to prepare an album."""
        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            lambda barcode: None,
        )
        response = await client.post(
            "/api_v1/musicbrainz/prepare", json={"albumId": self._album_id}
        )
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"

        assert data["album_id"] == self._album_id
        assert data["release"]["album"] == "The Album"
        assert data["release"]["albumartist"] == "The Artist"
        assert data["release"]["year"] == 2017
        assert data["release"]["barcode"] == "0723540055629"

        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["title"] == "Track 1"
        assert data["tracks"][0]["isrc"] == "QZ5AB1840341"
        assert data["tracks"][1]["title"] == "Track 2"
        assert "isrc" not in data["tracks"][1]

        assert data["flags"]["on_musicbrainz"] is False
        assert data["flags"]["missing_isrc"] == ["Track 2"]
        assert data["flags"]["missing"] == ["catalognum", "country"]

        checklist = {c["key"]: c for c in data["checklist"]}
        assert checklist["title"]["filled"] is True
        assert checklist["barcode"]["filled"] is True
        assert checklist["isrc"]["filled"] is False

    async def test_prepare_unknown_album(self, client):
        """Test preparing an album that does not exist returns 404."""
        response = await client.post(
            "/api_v1/musicbrainz/prepare", json={"albumId": 999999}
        )
        assert response.status_code == 404, "Response status code is not 404"

    async def test_prepare_invalid_body(self, client):
        """Test preparing an album with an invalid request body returns 400."""
        response = await client.post(
            "/api_v1/musicbrainz/prepare", json={"albumId": "not-an-int"}
        )
        assert response.status_code == 400, "Response status code is not 400"

        response = await client.post("/api_v1/musicbrainz/prepare", json={})
        assert response.status_code == 400, "Response status code is not 400"

    async def test_album_exists_stored_mbid(self, client):
        """An album with a stored MBID is reported without a lookup."""
        self.beets_lib.get_album(self._album_id)["mb_albumid"] = MBID_A
        self.beets_lib._db.commit()

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_id}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {
            "album_id": self._album_id,
            "exists": True,
            "mbid": MBID_A,
        }

    async def test_album_exists_barcode_match(self, client, monkeypatch):
        """A high-score barcode match reports the album as present."""
        match = {
            "mbid": MBID_A,
            "title": "The Album",
            "artist": "The Artist",
            "score": 100,
        }
        seen = {}

        def fake_search(barcode):
            seen["barcode"] = barcode
            return [match]

        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            fake_search,
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_id}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {"album_id": self._album_id, "exists": True, "mbid": MBID_A}
        assert seen["barcode"] == BARCODE

    async def test_album_exists_low_score_no_match(self, client, monkeypatch):
        """A weak barcode match reports the album as not present."""
        match = {"mbid": MBID_A, "title": "Other", "artist": "Other", "score": 30}
        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            lambda barcode: [match],
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_id}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {"album_id": self._album_id, "exists": False, "mbid": None}

    async def test_album_exists_no_barcode(self, client, monkeypatch):
        """An album without a barcode cannot be looked up."""
        self.beets_lib.get_album(self._album_id)["barcode"] = ""
        self.beets_lib._db.commit()

        called = []

        def fake_search(barcode):
            called.append(barcode)
            return []

        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            fake_search,
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_id}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {"album_id": self._album_id, "exists": False, "mbid": None}
        assert called == []

    async def test_album_exists_failed_lookup(self, client, monkeypatch):
        """A failed lookup does not guess and reports not present."""
        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            lambda barcode: None,
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_id}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {"album_id": self._album_id, "exists": False, "mbid": None}

    async def test_album_exists_unknown_album(self, client):
        """Test that an unknown album returns 404."""
        response = await client.get("/api_v1/musicbrainz/album_exists/999999")
        assert response.status_code == 404, "Response status code is not 404"


class TestMusicbrainzInboxEndpoint:
    """Inbox-based MusicBrainz preparation endpoints.

    The inbox endpoints work on folders (album folders with music files on
    disk) instead of the beets library, using the match of their most recent
    import session when one exists.
    """

    _inbox: Path | None = None
    _album: Path | None = None

    @pytest.fixture(autouse=True, scope="class")
    def inbox(self, tmpdir_factory):
        """Configure an inbox folder that contains one real album."""
        inbox_path = Path(tmpdir_factory.mktemp("inbox"))
        album_dir = inbox_path / "Antidote"
        album_dir.mkdir()
        source = (
            Path(__file__).parents[3]
            / "data"
            / "audio"
            / "Annix"
            / "Antidote"
            / "01 Antidote.mp3"
        )
        shutil.copy(source, album_dir / "01 Antidote.mp3")

        config = get_config()
        config["gui"]["inbox"]["folders"] = {
            "inbox1": {"path": str(inbox_path), "autotag": "preview"}
        }

        self._inbox = inbox_path
        self._album = album_dir
        yield inbox_path
        refresh_config()

    def _album_segment(self) -> str:
        # Slashes are percent-encoded so the path fits a single URL segment.
        return quote(str(self._album), safe="")

    async def test_albums_lists_inbox_folder(self, client):
        """The albums endpoint lists inbox folders with no match info."""
        response = await client.get("/api_v1/musicbrainz/albums")
        data = await response.get_json()
        assert response.status_code == 200

        album = next((a for a in data if a["folder_path"] == str(self._album)), None)
        assert album is not None
        assert album["type"] == "directory"
        assert album["has_session"] is False
        assert album["has_match"] is False
        assert album["name"] is None
        assert album["match_percentage"] is None

    async def test_albums_with_session_match(self, client, monkeypatch):
        """The albums endpoint surfaces the session's match percentage."""
        best = SimpleNamespace(
            distance=SimpleNamespace(distance=0.0889),
            match=SimpleNamespace(
                info=SimpleNamespace(
                    data_url=f"https://musicbrainz.org/release/{MBID_A}"
                )
            ),
            album="Antidote",
            artist="Annix",
        )
        task = SimpleNamespace(
            current_metadata={
                "album": "Antidote",
                "albumartist": "Annix",
                "year": "2021",
            },
            best_candidate_state=best,
        )
        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources._folder_task",
            lambda folder: task,
        )

        response = await client.get("/api_v1/musicbrainz/albums")
        data = await response.get_json()
        assert response.status_code == 200

        album = next((a for a in data if a["folder_path"] == str(self._album)), None)
        assert album is not None
        assert album["has_session"] is True
        assert album["has_match"] is True
        assert album["match_percentage"] == 91.1
        assert album["match_mbid"] == MBID_A

    async def test_prepare_folder(self, client):
        """The folder can be prepared from the tags of its music files."""
        response = await client.get(
            f"/api_v1/musicbrainz/prepare/{self._album_segment()}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data["folder_path"] == str(self._album)
        assert data["album_id"] == 0  # not stored in the beets library
        assert data["release"]["album"] == "Antidote"
        assert data["release"]["year"] == 2021
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["title"] == "Antidote"

    async def test_prepare_folder_unknown(self, client):
        """A path that is not an album folder returns 404."""
        response = await client.get(
            f"/api_v1/musicbrainz/prepare/{quote(str(self._inbox), safe='')}"
        )
        assert response.status_code == 404

    async def test_prepare_folder_unquotes_path(self, client):
        """Percent-encoded paths (slashes as %2F) are decoded server side."""
        encoded = quote(str(self._album), safe="")
        response = await client.get(f"/api_v1/musicbrainz/prepare/{encoded}")
        assert response.status_code == 200
        data = await response.get_json()
        assert data["folder_path"] == str(self._album)

    async def test_album_exists_inbox_no_match(self, client, monkeypatch):
        """Without a session the barcode is read from the files, not hit."""
        called = []

        def fake_search(barcode):
            called.append(barcode)
            return []

        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            fake_search,
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_segment()}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {
            "folder_path": str(self._album),
            "exists": False,
            "mbid": None,
        }
        # The test file has no barcode tag, so no lookup happens.
        assert called == []

    async def test_album_exists_inbox_session_match(self, client, monkeypatch):
        """A close session match reports the album as present."""
        best = SimpleNamespace(
            distance=SimpleNamespace(distance=0.0),
            match=SimpleNamespace(
                info=SimpleNamespace(
                    data_url=f"https://musicbrainz.org/release/{MBID_A}"
                )
            ),
        )
        task = SimpleNamespace(
            current_metadata={"barcode": BARCODE},
            best_candidate_state=best,
        )
        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources._folder_task",
            lambda folder: task,
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_segment()}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {
            "folder_path": str(self._album),
            "exists": True,
            "mbid": MBID_A,
        }

    async def test_album_exists_inbox_barcode_lookup(self, client, monkeypatch):
        """Without a close match the release is looked up by barcode."""
        best = SimpleNamespace(
            distance=SimpleNamespace(distance=0.9),
            match=SimpleNamespace(info=SimpleNamespace(data_url=None)),
        )
        task = SimpleNamespace(
            current_metadata={"barcode": BARCODE},
            best_candidate_state=best,
        )
        seen = {}

        def fake_search(barcode):
            seen["barcode"] = barcode
            return [{"mbid": MBID_A, "title": "The Album", "score": 100}]

        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources._folder_task",
            lambda folder: task,
        )
        monkeypatch.setattr(
            "beets_flask.server.routes.musicbrainz.resources.search_release_by_barcode",
            fake_search,
        )

        response = await client.get(
            f"/api_v1/musicbrainz/album_exists/{self._album_segment()}"
        )
        data = await response.get_json()
        assert response.status_code == 200
        assert data == {
            "folder_path": str(self._album),
            "exists": True,
            "mbid": MBID_A,
        }
        assert seen["barcode"] == BARCODE
