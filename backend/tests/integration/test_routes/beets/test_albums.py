"""Tests for the new beets albums API endpoints.

Covers the implemented endpoints of ``beets_flask/server/routes/beets/albums.py``:

- ``GET /api_v1/beets/albums/<album_id>``
- ``PATCH /api_v1/beets/albums/<album_id>``
- ``DELETE /api_v1/beets/albums/<album_id>``
- ``GET /api_v1/beets/albums/`` (bulk)
- ``PATCH /api_v1/beets/albums/`` (bulk)
- ``DELETE /api_v1/beets/albums/`` (bulk)
"""

import json
import os
from pathlib import Path

import pytest
from beets.library import Album
from quart.typing import TestClientProtocol as Client

from beets_flask.config import get_config
from beets_flask.server.routes.beets._cursor import Cursor
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin


def _album_url(album_id: int) -> str:
    """Build the URL for a single album resource."""
    return f"/api_v1/beets/albums/{album_id}"


def _assert_album_document(data: dict, album: Album) -> None:
    """Assert the JSON:API-ish shape of a single-album document.

    Verifies type, id and attributes, and that the relationships reference
    exactly the items of ``album`` (i.e. no items of other albums).
    """
    assert data["data"]["type"] == "album"
    assert data["data"]["id"] == str(album.id)
    assert data["data"]["attributes"] == {"title": album.album}
    rel_ids = {r["id"] for r in data["data"]["relationships"]}
    assert rel_ids == {str(i.id) for i in album.items()}, (
        "Relationships do not match the album's items"
    )
    assert all(r["type"] == "item" for r in data["data"]["relationships"])


def _assert_included_items(data: dict, album: Album) -> None:
    """Assert that ``included`` contains exactly the items of ``album``."""
    items = album.items()
    included = {i["id"]: i for i in data["included"]}
    assert set(included) == {str(i.id) for i in items}
    for item in items:
        assert included[str(item.id)]["attributes"] == {"title": item.title}


# ----------------------------------- Get ----------------------------------- #


class TestGetAlbum(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/albums/<album_id>``."""

    _albums: dict[str, Album] = {}

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create the albums used by all tests in this class.

        - ``"a"``: album with two items
        - ``"b"``: album with one item
        - ``"c"``: album without items
        """
        a = beets_lib_album(album="Album A", albumartist="Artist One")
        self.beets_lib.add(a)
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 1"))
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 2"))

        b = beets_lib_album(album="Album B", albumartist="Artist Two")
        self.beets_lib.add(b)
        self.beets_lib.add(beets_lib_item(album_id=b.id, title="Track 3"))

        c = beets_lib_album(album="Album C", albumartist="Artist Three")
        self.beets_lib.add(c)

        self._albums.update(a=a, b=b, c=c)

    @pytest.mark.parametrize(
        "album_key, include, n_included",
        [
            ("a", None, 0),
            ("a", "items", 2),
            ("b", "items", 1),
            ("c", "items", 0),
        ],
        ids=["plain", "a_with_items", "b_with_items", "c_without_items"],
    )
    async def test_get_album(
        self, client: Client, album_key: str, include: str | None, n_included: int
    ):
        """GET a single album, with or without its items included."""
        album = self.beets_lib.get_album(self._albums[album_key].id)
        assert album is not None

        query = f"?include={include}" if include else ""
        response = await client.get(_album_url(album.id) + query)
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        _assert_album_document(data, album)
        assert len(data["included"]) == n_included
        if include == "items":
            _assert_included_items(data, album)

    async def test_get_album_not_found(self, client: Client):
        """GET a non-existent album -> 404."""
        response = await client.get(_album_url(999999))
        data = await response.get_json()

        assert response.status_code == 404, "Response status code is not 404"
        assert data["type"] == "NotFoundException"
        assert "999999" in data["message"], "Error message does not name the album id"

    async def test_get_album_invalid_include(self, client: Client):
        """GET with an unsupported ``include`` value -> 400."""
        response = await client.get(_album_url(self._albums["a"].id) + "?include=bogus")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"


# ---------------------------------- Patch ---------------------------------- #


class TestPatchAlbum(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/albums/<album_id>``."""

    _albums: dict[str, Album] = {}

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create the albums used by all tests in this class.

        - ``"a"``: modified by the title tests
        - ``"b"``: never modified (noop test)
        - ``"c"``: only read (readonly test)
        """
        a = beets_lib_album(album="Patchable Album", albumartist="Artist One")
        self.beets_lib.add(a)
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 1"))

        b = beets_lib_album(album="Noop Album", albumartist="Artist Two")
        self.beets_lib.add(b)

        c = beets_lib_album(album="Readonly Album", albumartist="Artist Three")
        self.beets_lib.add(c)

        self._albums.update(a=a, b=b, c=c)

    @pytest.mark.parametrize("include", [None, "items"], ids=["plain", "with_items"])
    async def test_patch_album_title(self, client: Client, include: str | None):
        """PATCH the album title, with or without its items included."""
        album = self.beets_lib.get_album(self._albums["a"].id)
        assert album is not None
        new_title = "Updated Title"
        query = f"?include={include}" if include else ""

        response = await client.patch(
            _album_url(album.id) + query, json={"title": new_title}
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["attributes"]["title"] == new_title

        # The change must be persisted and the response must match the new state
        stored = self.beets_lib.get_album(album.id)
        assert stored is not None
        assert stored.album == new_title, "Title was not updated in the beets library"
        _assert_album_document(data, stored)
        if include == "items":
            _assert_included_items(data, stored)

    async def test_patch_album_does_not_touch_other_albums(self, client: Client):
        """PATCHing one album must leave other albums unchanged."""
        album = self.beets_lib.get_album(self._albums["a"].id)
        assert album is not None

        other = beets_lib_album(album="Untouched Album", albumartist="Other Artist")
        self.beets_lib.add(other)

        response = await client.patch(
            _album_url(album.id), json={"title": "Changed Title"}
        )
        assert response.status_code == 200, "Response status code is not 200"

        stored_other = self.beets_lib.get_album(other.id)
        assert stored_other is not None
        assert stored_other.album == "Untouched Album", (
            "Patching one album changed another album"
        )

    async def test_patch_album_not_found(self, client: Client):
        """PATCH a non-existent album -> 404."""
        response = await client.patch(
            _album_url(999999), json={"title": "Does Not Matter"}
        )
        data = await response.get_json()

        assert response.status_code == 404, "Response status code is not 404"
        assert data["type"] == "NotFoundException"

    async def test_patch_album_empty_body_is_noop(self, client: Client):
        """PATCH with an empty body must not change anything."""
        album = self.beets_lib.get_album(self._albums["b"].id)
        assert album is not None

        response = await client.patch(_album_url(album.id), json={})
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["attributes"]["title"] == album.album

        stored = self.beets_lib.get_album(album.id)
        assert stored is not None
        assert stored.album == album.album, "Album was modified by an empty patch"

    async def test_patch_album_readonly(self, client: Client):
        """PATCH must fail and not modify the album when the library is read-only."""
        album = self.beets_lib.get_album(self._albums["c"].id)
        assert album is not None

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.patch(
                _album_url(album.id), json={"title": "Should Not Apply"}
            )
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

        stored = self.beets_lib.get_album(album.id)
        assert stored is not None
        assert stored.album == album.album, (
            "Album was modified even though the library is read-only"
        )


# ---------------------------------- Delete --------------------------------- #


class TestDeleteAlbum(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/albums/<album_id>``."""

    _albums: dict[str, Album] = {}

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create the albums used by all tests in this class.

        - ``"a"``: deleted by the delete test
        - ``"b"``: never deleted (readonly test)
        """
        a = beets_lib_album(album="Delete Album", albumartist="Artist One")
        self.beets_lib.add(a)
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 1"))
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 2"))

        b = beets_lib_album(album="Keep Album", albumartist="Artist Two")
        self.beets_lib.add(b)
        self.beets_lib.add(beets_lib_item(album_id=b.id, title="Track 3"))

        self._albums.update(a=a, b=b)

    async def test_delete_album(self, client: Client):
        """DELETE a single album, removing it and all of its items."""
        album = self.beets_lib.get_album(self._albums["a"].id)
        assert album is not None
        item_ids = [i.id for i in album.items()]

        response = await client.delete(_album_url(album.id))
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["id"] == str(album.id)
        assert data["data"]["attributes"] == {"title": album.album}
        rel_ids = {r["id"] for r in data["data"]["relationships"]}
        assert rel_ids == {str(i) for i in item_ids}
        assert data["included"] == []

        # Album and its items are gone, other albums are untouched
        assert self.beets_lib.get_album(album.id) is None, (
            "Album was not removed from the beets library"
        )
        for item_id in item_ids:
            assert self.beets_lib.get_item(item_id) is None, (
                "Album's items were not removed from the beets library"
            )
        assert self.beets_lib.get_album(self._albums["b"].id) is not None

    async def test_delete_album_not_found(self, client: Client):
        """DELETE a non-existent album -> 404."""
        response = await client.delete(_album_url(999999))
        data = await response.get_json()

        assert response.status_code == 404, "Response status code is not 404"
        assert data["type"] == "NotFoundException"

    async def test_delete_album_readonly(self, client: Client):
        """DELETE must fail and not modify the album when the library is read-only."""
        album = self.beets_lib.get_album(self._albums["b"].id)
        assert album is not None

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.delete(_album_url(album.id))
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

        assert self.beets_lib.get_album(album.id) is not None, (
            "Album was removed even though the library is read-only"
        )


class TestDeleteAlbumFiles(IsolatedBeetsLibraryMixin):
    """Tests for the ``delete_files`` parameter of the album delete endpoint."""

    _albums: dict[str, Album] = {}

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create albums with dedicated files on disk."""
        for key, file_name in (
            ("keep", "album_delete_keep.mp3"),
            ("delete", "album_delete_remove.mp3"),
            ("keep_false", "album_delete_false.mp3"),
        ):
            a = beets_lib_album(album=f"Album {key}", albumartist="Artist")
            self.beets_lib.add(a)
            item = beets_lib_item(album_id=a.id, title=f"Track {key}")
            self.beets_lib.add(item)
            path = Path(os.environ["HOME"]) / "audio" / file_name
            path.write_bytes(b"fake mp3")
            item.path = str(path).encode()
            item.store()
            self._albums[key] = a

    async def test_delete_album_keeps_files_by_default(self, client: Client):
        """DELETE without ``delete_files`` keeps the files on disk."""
        album = self._albums["keep"]
        path = Path(os.environ["HOME"]) / "audio" / "album_delete_keep.mp3"
        assert path.exists()

        response = await client.delete(_album_url(album.id))

        assert response.status_code == 200, "Response status code is not 200"
        assert path.exists(), "Files were deleted although delete_files was not set"

    async def test_delete_album_with_files(self, client: Client):
        """DELETE with ``delete_files=true`` also removes the files from disk."""
        album = self._albums["delete"]
        path = Path(os.environ["HOME"]) / "audio" / "album_delete_remove.mp3"
        assert path.exists()

        response = await client.delete(_album_url(album.id) + "?delete_files=true")

        assert response.status_code == 200, "Response status code is not 200"
        assert not path.exists(), "Files were not deleted although delete_files=true"

    async def test_delete_album_delete_files_false(self, client: Client):
        """DELETE with ``delete_files=false`` keeps the files on disk."""
        album = self._albums["keep_false"]
        path = Path(os.environ["HOME"]) / "audio" / "album_delete_false.mp3"
        assert path.exists()

        response = await client.delete(_album_url(album.id) + "?delete_files=false")

        assert response.status_code == 200, "Response status code is not 200"
        assert path.exists(), "Files were deleted although delete_files=false"


# ---------------------------------- Bulk Get --------------------------------- #


class TestGetAlbums(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/albums/`` (bulk)."""

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create 25 albums with distinct titles and five artists."""
        for i in range(25):
            self.beets_lib.add(
                beets_lib_album(
                    album=f"Bulk Album {i:02d}", albumartist=f"Artist{i % 5}"
                )
            )

    async def test_get_albums_pagination(self, client: Client):
        """Iterate all pages via the ``links.next`` cursor."""
        next_url = "/api_v1/beets/albums/?limit=10"
        titles = []
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 25
            assert "self" in data["links"]
            titles.extend(i["attributes"]["title"] for i in data["data"])
            pages += 1
            next_url = data["links"].get("next")

        assert pages == 3, "Expected three pages of ten albums"
        assert len(titles) == 25, "Not all albums were returned"
        assert len(set(titles)) == 25, "Albums were returned more than once"

    async def test_get_albums_default_limit(self, client: Client):
        """Without ``limit``, the default page size applies."""
        response = await client.get("/api_v1/beets/albums/")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert len(data["data"]) == 25
        assert "next" not in data.get("links", {}), "Unexpected next page"

    async def test_get_albums_sort(self, client: Client):
        """Sort by album title ascending and descending."""
        response = await client.get("/api_v1/beets/albums/?sort=album&limit=100")
        data = await response.get_json()
        titles = [i["attributes"]["title"] for i in data["data"]]
        assert titles == sorted(titles), "Albums are not sorted ascending"

        response = await client.get("/api_v1/beets/albums/?sort=-album&limit=100")
        data = await response.get_json()
        titles = [i["attributes"]["title"] for i in data["data"]]
        assert titles == sorted(titles, reverse=True), (
            "Albums are not sorted descending"
        )

    async def test_get_albums_descending_pagination(self, client: Client):
        """Iterate all pages sorted descending via the cursor."""
        next_url = "/api_v1/beets/albums/?sort=-album&limit=5"
        titles = []
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 25
            titles.extend(i["attributes"]["title"] for i in data["data"])
            pages += 1
            next_url = data["links"].get("next")

        assert pages == 5, "Expected five pages of five albums"
        assert titles == sorted(titles, reverse=True), (
            "Albums are not sorted descending"
        )
        assert len(titles) == 25, "Not all albums were returned"

    async def test_get_albums_filter_query(self, client: Client):
        """Filter by a beets query string."""
        response = await client.get(
            "/api_v1/beets/albums/?filter_query=albumartist:Artist2"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        expected = {f"Bulk Album {i:02d}" for i in range(25) if i % 5 == 2}
        titles = {i["attributes"]["title"] for i in data["data"]}
        assert titles == expected, "Filtered albums do not match the query"
        assert data["meta"]["total"] == 5

    async def test_get_albums_invalid_filter_query(self, client: Client):
        """A filter value that does not match its field type -> 400."""
        response = await client.get(
            "/api_v1/beets/albums/?filter_query=year:notanumber"
        )
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_cursor_with_invalid_filter(self, client: Client):
        """A cursor token carrying an unparseable filter query -> 400."""
        token = json.dumps({"s": "-added", "q": "year:notanumber"}).encode().hex()
        response = await client.get(f"/api_v1/beets/albums/?cursor={token}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_filter_ids(self, client: Client):
        """Filter by explicit ids."""
        ids = [str(a.id) for a in list(self.beets_lib.albums())[:2]]
        response = await client.get(
            "/api_v1/beets/albums/?filter_ids=" + "&filter_ids=".join(ids)
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert {i["id"] for i in data["data"]} == set(ids)
        assert data["meta"]["total"] == 2

    async def test_get_albums_filter_ids_single(self, client: Client):
        """A single ``filter_ids`` value is accepted."""
        album = list(self.beets_lib.albums())[0]

        response = await client.get(f"/api_v1/beets/albums/?filter_ids={album.id}")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert data["data"][0]["id"] == str(album.id)

    async def test_get_albums_invalid_filter_ids(self, client: Client):
        """A non-numeric ``filter_ids`` value -> 400."""
        response = await client.get("/api_v1/beets/albums/?filter_ids=abc")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_albums_cursor_with_invalid_filter_ids(self, client: Client):
        """A cursor token carrying non-numeric filter ids -> 400."""
        token = json.dumps({"s": "-added", "f": ["abc"]}).encode().hex()
        response = await client.get(f"/api_v1/beets/albums/?cursor={token}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_empty(self, client: Client):
        """A filter without matches returns an empty page."""
        response = await client.get(
            "/api_v1/beets/albums/?filter_query=album:Nonexistent"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"] == []
        assert data["meta"]["total"] == 0
        assert "next" not in data.get("links", {})

    async def test_get_albums_invalid_cursor(self, client: Client):
        """An invalid cursor token -> 400."""
        response = await client.get("/api_v1/beets/albums/?cursor=bogus")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_invalid_sort_field(self, client: Client):
        """Sorting by a disallowed field -> 400."""
        response = await client.get("/api_v1/beets/albums/?sort=+bogus")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_albums_limit_too_high(self, client: Client):
        """A limit above the maximum -> 400."""
        response = await client.get("/api_v1/beets/albums/?limit=100000")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    @pytest.mark.parametrize("limit", ["0", "-1"], ids=["zero", "negative"])
    async def test_get_albums_limit_too_low(self, client: Client, limit: str):
        """A non-positive limit -> 400."""
        response = await client.get(f"/api_v1/beets/albums/?limit={limit}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_empty_sort(self, client: Client):
        """An empty ``sort`` value -> 400."""
        response = await client.get("/api_v1/beets/albums/?sort=&limit=100")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_albums_sort_without_field(self, client: Client):
        """A ``sort`` without a field -> 400."""
        response = await client.get("/api_v1/beets/albums/?sort=,&limit=100")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_albums_sort_sign_without_field(self, client: Client):
        """A sort sign without a field -> 400."""
        response = await client.get("/api_v1/beets/albums/?sort=%2B")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_albums_cursor_with_crafted_sort(self, client: Client):
        """A cursor token with a crafted sort field -> 400."""
        token = json.dumps({"s": "+bogus", "v": "x", "i": 1}).encode().hex()
        response = await client.get(f"/api_v1/beets/albums/?cursor={token}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_cursor_with_sort_rejected(self, client: Client):
        """``cursor`` combined with ``sort`` -> 400."""
        token = Cursor.initial("+album").to_string()
        response = await client.get(f"/api_v1/beets/albums/?cursor={token}&sort=album")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_albums_cursor_with_filter_rejected(self, client: Client):
        """``cursor`` combined with filters -> 400."""
        token = Cursor.initial("+album").to_string()
        for params in ("filter_query=albumartist:Artist2", "filter_ids=1&filter_ids=2"):
            response = await client.get(
                f"/api_v1/beets/albums/?cursor={token}&{params}"
            )
            data = await response.get_json()
            assert response.status_code == 400, f"{params} should be rejected"
            assert data["type"] == "InvalidUsageException"

    async def test_get_albums_filtered_pagination(self, client: Client):
        """Filters survive pagination via the self-contained cursor."""
        next_url = "/api_v1/beets/albums/?filter_query=albumartist:Artist2&limit=2"
        titles = []
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 5
            titles.extend(i["attributes"]["title"] for i in data["data"])
            pages += 1
            next_url = data["links"].get("next")
            if next_url:
                # The cursor is self-contained: no filter params in the link
                for param in ("filter_query", "filter_ids", "sort"):
                    assert f"{param}=" not in next_url, f"{param} in next link"

        expected = {f"Bulk Album {i:02d}" for i in range(25) if i % 5 == 2}
        assert pages == 3, "Expected three pages of two albums"
        assert set(titles) == expected, "Filtered albums do not match the query"
        assert len(titles) == 5, "Albums were returned more than once"

    async def test_get_albums_filtered_pagination_by_ids(self, client: Client):
        """Id filters survive pagination via the self-contained cursor."""
        ids = [str(a.id) for a in list(self.beets_lib.albums())[:3]]
        next_url = "/api_v1/beets/albums/?limit=2&filter_ids=" + "&filter_ids=".join(
            ids
        )
        found = []
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 3
            found.extend(i["id"] for i in data["data"])
            next_url = data["links"].get("next")

        assert set(found) == set(ids), "Id filtered pagination lost albums"
        assert len(found) == 3

    async def test_get_albums_next_link_strips_sort(self, client: Client):
        """The ``links.next`` of a sorted page carries no ``sort`` and stays sorted."""
        response = await client.get("/api_v1/beets/albums/?sort=album&limit=5")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        first_titles = [i["attributes"]["title"] for i in data["data"]]
        assert first_titles == sorted(first_titles)

        next_url = data["links"]["next"]
        assert "sort=" not in next_url, "Next link must not carry the sort parameter"

        response = await client.get(next_url)
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        second_titles = [i["attributes"]["title"] for i in data["data"]]
        assert second_titles == sorted(second_titles)
        # The second page continues the same order after the first page
        assert all(t1 < t2 for t1 in first_titles for t2 in second_titles)

    async def test_get_albums_include_items(self, client: Client):
        """``include=items`` embeds the albums' items in ``included``."""
        a = beets_lib_album(album="Inc Album A", albumartist="IncArtist")
        self.beets_lib.add(a)
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="T1"))
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="T2"))
        b = beets_lib_album(album="Inc Album B", albumartist="IncArtist")
        self.beets_lib.add(b)
        self.beets_lib.add(beets_lib_item(album_id=b.id, title="T3"))

        response = await client.get(
            "/api_v1/beets/albums/?filter_query=albumartist:IncArtist"
            "&include=items&limit=10"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert len(data["data"]) == 2
        included = {i["id"] for i in data["included"]}
        expected = {
            str(i.id)
            for album in self.beets_lib.albums("albumartist:IncArtist")
            for i in album.items()
        }
        assert included == expected, "Included items do not match the albums' items"

    async def test_get_albums_include_items_pagination(self, client: Client):
        """The next page link keeps ``include=items``."""
        for i in range(15):
            a = beets_lib_album(album=f"Inc Page {i:02d}", albumartist="IncPageArtist")
            self.beets_lib.add(a)
            self.beets_lib.add(beets_lib_item(album_id=a.id, title=f"T{i}"))

        next_url = (
            "/api_v1/beets/albums/?filter_query=albumartist:IncPageArtist"
            "&include=items&limit=10"
        )
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert len(data["data"]) == len(data["included"]), (
                "Each album must contribute exactly one item"
            )
            pages += 1
            next_url = data["links"].get("next")
            if next_url:
                assert "include=items" in next_url, "Next link must keep include"

        assert pages == 2, "Expected two pages of ten and five albums"


# -------------------------------- Bulk Delete ------------------------------- #


class TestDeleteAlbums(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/albums/`` (bulk)."""

    def _add_album(
        self,
        album: str,
        artist: str,
        n_items: int = 1,
        file_names: list[str] | None = None,
    ) -> Album:
        """Add an album with items, optionally with dedicated audio files.

        Each test creates the albums it needs, so the tests are independent
        of each other and of their execution order.
        """
        a = beets_lib_album(album=album, albumartist=artist, artpath=None)
        self.beets_lib.add(a)
        for i in range(n_items):
            item = beets_lib_item(album_id=a.id, title=f"Track {i}")
            self.beets_lib.add(item)
            if file_names and i < len(file_names):
                path = Path(os.environ["HOME"]) / "audio" / file_names[i]
                path.write_bytes(b"fake mp3")
                item.path = str(path).encode()
                item.store()
        return a

    async def test_delete_albums_filter_query(self, client: Client):
        """DELETE removes only the albums matching the filter."""
        a = self._add_album("Album A", "GroupA")
        b = self._add_album("Album B", "GroupA")
        c = self._add_album("Album C", "GroupB")

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=albumartist:GroupA"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self.beets_lib.get_album(a.id) is None, "Album A was not deleted"
        assert self.beets_lib.get_album(b.id) is None, "Album B was not deleted"
        assert self.beets_lib.get_album(c.id) is not None, (
            "Album of the other group was deleted"
        )

    async def test_delete_albums_invalid_filter_query(self, client: Client):
        """DELETE with an unparseable filter query -> 400, nothing deleted."""
        album = self._add_album("Album A", "InvalidQueryGroup")

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=year:notanumber"
        )
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self.beets_lib.get_album(album.id) is not None, "Album was deleted"

    async def test_delete_albums_filter_ids(self, client: Client):
        """DELETE removes only the albums with the given ids."""
        a = self._add_album("Album A", "Artist A")
        b = self._add_album("Album B", "Artist B")
        c = self._add_album("Album C", "Artist C")

        response = await client.delete(
            "/api_v1/beets/albums/?filter_ids="
            + "&filter_ids=".join(map(str, [a.id, b.id]))
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self.beets_lib.get_album(a.id) is None, "Album A was not deleted"
        assert self.beets_lib.get_album(b.id) is None, "Album B was not deleted"
        assert self.beets_lib.get_album(c.id) is not None, (
            "Album without a matching id was deleted"
        )

    async def test_delete_albums_no_filter(self, client: Client):
        """DELETE without a filter removes all albums."""
        for i in range(3):
            self._add_album(f"Album {i}", f"Artist {i}")
        expected = len(list(self.beets_lib.albums()))

        response = await client.delete("/api_v1/beets/albums/")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == expected
        assert list(self.beets_lib.albums()) == [], "Library is not empty"

    async def test_delete_albums_no_match(self, client: Client):
        """A filter without matches deletes nothing and reports zero."""
        album = self._add_album("Kept Album", "KeptArtist")

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=album:Nonexistent"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 0
        assert self.beets_lib.get_album(album.id) is not None, "Album was deleted"

    async def test_delete_albums_readonly(self, client: Client):
        """DELETE must fail and not modify the library when it is read-only."""
        album = self._add_album("Readonly Album", "ReadonlyArtist")

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.delete(
                "/api_v1/beets/albums/?filter_query=albumartist:ReadonlyArtist"
            )
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self.beets_lib.get_album(album.id) is not None, (
            "Album was removed even though the library is read-only"
        )

    async def test_delete_albums_removes_items(self, client: Client):
        """DELETE removes the album's items from the library as well."""
        album = self._add_album("Album With Items", "ItemArtist", n_items=2)
        stored = self.beets_lib.get_album(album.id)
        assert stored is not None
        item_ids = [i.id for i in stored.items()]

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=albumartist:ItemArtist"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert self.beets_lib.get_album(album.id) is None, "Album was not removed"
        for item_id in item_ids:
            assert self.beets_lib.get_item(item_id) is None, (
                "Album's items were not removed from the library"
            )

    async def test_delete_albums_keeps_files_by_default(self, client: Client):
        """DELETE without ``delete_files`` keeps the files on disk."""
        self._add_album(
            "Keep Files Album", "KeepArtist", file_names=["album_bulk_keep.mp3"]
        )
        path = Path(os.environ["HOME"]) / "audio" / "album_bulk_keep.mp3"
        assert path.exists()

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=albumartist:KeepArtist"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert path.exists(), "Files were deleted without delete_files"

    async def test_delete_albums_with_delete_files(self, client: Client):
        """DELETE with ``delete_files=true`` also removes the files from disk."""
        self._add_album(
            "Remove Files Album", "RemoveArtist", file_names=["album_bulk_rm.mp3"]
        )
        path = Path(os.environ["HOME"]) / "audio" / "album_bulk_rm.mp3"
        assert path.exists()

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=albumartist:RemoveArtist"
            "&delete_files=true"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert not path.exists(), "Files were not deleted although delete_files=true"

    async def test_delete_albums_delete_files_false(self, client: Client):
        """DELETE with an explicit ``delete_files=false`` keeps the files."""
        self._add_album(
            "False Files Album", "FalseArtist", file_names=["album_bulk_false.mp3"]
        )
        path = Path(os.environ["HOME"]) / "audio" / "album_bulk_false.mp3"
        assert path.exists()

        response = await client.delete(
            "/api_v1/beets/albums/?filter_query=albumartist:FalseArtist"
            "&delete_files=false"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert path.exists(), "File was deleted although delete_files=false"


# --------------------------------- Bulk Patch -------------------------------- #


class TestPatchAlbums(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/albums/`` (bulk)."""

    def _add_album(self, album: str, artist: str, n_items: int = 1) -> Album:
        """Add an album with items.

        Each test creates the albums it needs, so the tests are independent
        of each other and of their execution order.
        """
        a = beets_lib_album(album=album, albumartist=artist, artpath=None)
        self.beets_lib.add(a)
        for i in range(n_items):
            self.beets_lib.add(beets_lib_item(album_id=a.id, title=f"Track {i}"))
        return a

    def _titles_of(self, artist: str) -> set[str]:
        """The album titles of all albums by the given artist."""
        return {a.album for a in self.beets_lib.albums(f"albumartist:{artist}")}

    async def test_patch_albums_filter_query(self, client: Client):
        """PATCH applies the body to all albums matching the filter."""
        self._add_album("Album A", "GroupA")
        self._add_album("Album B", "GroupA")
        self._add_album("Album C", "GroupB")

        response = await client.patch(
            "/api_v1/beets/albums/?filter_query=albumartist:GroupA",
            json={"title": "Renamed"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self._titles_of("GroupA") == {"Renamed"}, "Albums were not updated"
        assert self._titles_of("GroupB") == {"Album C"}, "Other group was changed"

    async def test_patch_albums_invalid_filter_query(self, client: Client):
        """PATCH with an unparseable filter query -> 400, nothing updated."""
        self._add_album("Album A", "InvalidQueryGroup")

        response = await client.patch(
            "/api_v1/beets/albums/?filter_query=year:notanumber",
            json={"title": "Should Not Apply"},
        )
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self._titles_of("InvalidQueryGroup") == {"Album A"}, (
            "Albums were changed"
        )

    async def test_patch_albums_filter_ids(self, client: Client):
        """PATCH applies the body to the albums with the given ids."""
        a = self._add_album("Album A", "Artist A")
        b = self._add_album("Album B", "Artist B")
        c = self._add_album("Album C", "Artist C")

        response = await client.patch(
            "/api_v1/beets/albums/?filter_ids="
            + "&filter_ids=".join(map(str, [a.id, b.id])),
            json={"title": "Id Renamed"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self.beets_lib.get_album(a.id).album == "Id Renamed"
        assert self.beets_lib.get_album(b.id).album == "Id Renamed"
        assert self.beets_lib.get_album(c.id).album == "Album C", (
            "Album without a matching id was changed"
        )

    async def test_patch_albums_no_filter(self, client: Client):
        """PATCH without a filter applies the body to all albums."""
        for i in range(3):
            self._add_album(f"Album {i}", f"Artist {i}")
        total = len(list(self.beets_lib.albums()))

        response = await client.patch(
            "/api_v1/beets/albums/", json={"title": "All Renamed"}
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == total
        assert {a.album for a in self.beets_lib.albums()} == {"All Renamed"}

    async def test_patch_albums_no_match(self, client: Client):
        """A filter without matches updates nothing and reports zero."""
        album = self._add_album("Kept Album", "KeptArtist")

        response = await client.patch(
            "/api_v1/beets/albums/?filter_query=album:Nonexistent",
            json={"title": "Should Not Apply"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 0
        assert self.beets_lib.get_album(album.id).album == "Kept Album", (
            "Album was changed"
        )

    async def test_patch_albums_readonly(self, client: Client):
        """PATCH must fail and not modify the library when it is read-only."""
        album = self._add_album("Readonly Album", "ReadonlyArtist")

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.patch(
                "/api_v1/beets/albums/?filter_query=albumartist:ReadonlyArtist",
                json={"title": "Should Not Apply"},
            )
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self.beets_lib.get_album(album.id).album == "Readonly Album", (
            "Album was updated even though the library is read-only"
        )

    async def test_patch_albums_empty_body(self, client: Client):
        """PATCH with an empty body is a no-op, but reports the matched count."""
        self._add_album("Album A", "EmptyArtist")
        self._add_album("Album B", "EmptyArtist")
        before = self._titles_of("EmptyArtist")

        response = await client.patch(
            "/api_v1/beets/albums/?filter_query=albumartist:EmptyArtist", json={}
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self._titles_of("EmptyArtist") == before, "Empty body changed albums"

    async def test_patch_albums_writes_file_tags(self, client: Client):
        """PATCH writes the new album title into the items' file tags."""
        import shutil

        from mediafile import MediaFile

        album = beets_lib_album(
            album="File Tag Album", albumartist="FileTagArtist", artpath=None
        )
        self.beets_lib.add(album)
        item = beets_lib_item(album_id=album.id, title="File Tag Item")
        self.beets_lib.add(item)
        path = Path(os.environ["HOME"]) / "audio" / "album_patch_filetag.mp3"
        shutil.copy(
            Path(__file__).parent.parent.parent.parent / "data" / "audio" / "test.mp3",
            path,
        )
        item.path = str(path).encode()
        item.store()

        response = await client.patch(
            "/api_v1/beets/albums/?filter_query=albumartist:FileTagArtist",
            json={"title": "File Renamed"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert MediaFile(str(path)).album == "File Renamed", "File tag not updated"
