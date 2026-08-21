"""Tests for the new beets albums API endpoints.

Covers the implemented endpoints of ``beets_flask/server/routes/beets/albums.py``:

- ``GET /api_v1/beets/albums/<album_id>``
- ``PATCH /api_v1/beets/albums/<album_id>``

The bulk endpoints (``GET/PATCH/DELETE /api_v1/beets/albums/``) are not
implemented yet and are only tested to return 501.
"""

import pytest
from beets.library import Album
from quart.typing import TestClientProtocol as Client

from beets_flask.config import get_config
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin


def _album_url(album_id: int) -> str:
    """Build the URL for a single album resource."""
    return f"/api_v1/beets/albums/{album_id}"


class TestAlbumsEndpoint(IsolatedBeetsLibraryMixin):
    """Tests for the single-album beets endpoints (GET and PATCH)."""

    # Created once per class by the ``albums`` fixture and shared by all tests.
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

    def _assert_album_document(self, data: dict, album: Album) -> None:
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

    def _assert_included_items(self, data: dict, album: Album) -> None:
        """Assert that ``included`` contains exactly the items of ``album``."""
        items = album.items()
        included = {i["id"]: i for i in data["included"]}
        assert set(included) == {str(i.id) for i in items}
        for item in items:
            assert included[str(item.id)]["attributes"] == {"title": item.title}

    # ----------------------------------- Get ---------------------------------- #

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
        self._assert_album_document(data, album)
        assert len(data["included"]) == n_included
        if include == "items":
            self._assert_included_items(data, album)

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

    # ---------------------------------- Patch --------------------------------- #

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
        self._assert_album_document(data, stored)
        if include == "items":
            self._assert_included_items(data, stored)

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

    # -------------------------------- Not implemented ------------------------------- #

    @pytest.mark.parametrize("method", ["get", "patch", "delete"])
    async def test_bulk_albums_not_implemented(self, client: Client, method: str):
        """The bulk albums endpoints are not implemented yet -> 501."""
        response = await getattr(client, method)("/api_v1/beets/albums/", json={})
        data = await response.get_json()

        assert response.status_code == 501, "Response status code is not 501"
        assert data["type"] == "NotImplementedException"
