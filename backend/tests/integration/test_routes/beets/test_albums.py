from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

import pytest

from beets_flask.server.routes_next.beets._types import SingleAlbumDocument
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from quart.typing import TestClientProtocol

    from beets_flask.importer.types import BeetsAlbum


class TestGetAlbum(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/albums/<album_id>``."""

    _albums: ClassVar[dict[str, BeetsAlbum]] = {}

    @staticmethod
    def _url(album_id: int, include: str | None = None) -> str:
        "Build the URL for a single album resource."
        return f"/api_v1/beets/albums/{album_id}" + (
            f"?include={include}" if include else ""
        )

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
        self,
        client: TestClientProtocol,
        album_key: str,
        include: str | None,
        n_included: int,
    ):
        """GET a single album, with or without its items included."""
        album = self.beets_lib.get_album(self._albums[album_key].id)
        assert album is not None

        response = await client.get(self._url(album.id, include))
        assert response.status_code == 200

        data = SingleAlbumDocument.model_validate(await response.get_json())
        assert len(data.included or []) == n_included

    async def test_get_album_not_found(self, client: TestClientProtocol):
        """GET a non-existent album -> 404."""
        response = await client.get(self._url(999999))
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "999999" in data["message"]

    async def test_get_album_invalid_include(self, client: TestClientProtocol):
        """GET with an unsupported ``include`` value -> 400."""
        response = await client.get(self._url(self._albums["a"].id, "bogus"))
        assert response.status_code == 400

        data = await response.get_json()
        assert data["type"] == "QuerystringValidationError"


class TestPatchAlbum(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/albums/<album_id>``."""

    _albums: ClassVar[dict[str, BeetsAlbum]] = {}

    @staticmethod
    def _url(album_id: int) -> str:
        """Build the URL for a single album resource."""
        return f"/api_v1/beets/albums/{album_id}"

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create the albums used by all tests in this class.

        - ``"a"``: album with two items
        - ``"b"``: album with one item
        - ``"c"``: album without items, its attributes are cleared with nulls
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

    async def test_patch_album(self, client: TestClientProtocol):
        """PATCH updates the given attributes and persists them in the library."""
        album_id = self._albums["a"].id
        updates = {
            "album": "Album A Updated",
            "albumartist": "Artist One Updated",
            "year": 2020,
        }

        response = await client.patch(self._url(album_id), json=updates)
        assert response.status_code == 200

        document = SingleAlbumDocument.model_validate(await response.get_json())
        assert document.data.id == str(album_id)
        assert document.data.attributes.model_dump() == updates

        album = self.beets_lib.get_album(album_id)
        assert album is not None
        assert album.album == updates["album"]
        assert album.albumartist == updates["albumartist"]
        assert album.year == updates["year"]

    async def test_patch_album_partial(self, client: TestClientProtocol):
        """PATCH only the given attributes; absent ones are left unchanged."""
        album_id = self._albums["b"].id

        response = await client.patch(self._url(album_id), json={"album": "Album B2"})
        assert response.status_code == 200

        document = SingleAlbumDocument.model_validate(await response.get_json())
        attributes = document.data.attributes.model_dump()
        assert attributes["album"] == "Album B2"
        assert attributes["albumartist"] == "Artist Two", (
            "Unpatched attribute was changed"
        )
        assert attributes["year"] == 1, "Unpatched attribute was changed"

        album = self.beets_lib.get_album(album_id)
        assert album is not None
        assert album.album == "Album B2"
        assert album.albumartist == "Artist Two"
        assert album.year == 1

    async def test_patch_album_null_clears_attribute(self, client: TestClientProtocol):
        """PATCH with an explicit ``null`` clears the attribute.

        Beets fixed fields cannot hold NULL: ``None`` is normalized to the
        field's empty value on store (``''`` for strings, ``0`` for numbers).
        """
        album_id = self._albums["c"].id

        response = await client.patch(
            self._url(album_id), json={"album": None, "year": None}
        )
        assert response.status_code == 200

        document = SingleAlbumDocument.model_validate(await response.get_json())
        attributes = document.data.attributes.model_dump()

        # The null value normilization is a bit weird!
        # We might need to change this in beets!
        assert attributes["album"] == ""
        assert attributes["year"] == 0
        assert attributes["albumartist"] == "Artist Three", (
            "Unpatched attribute was changed"
        )

        album = self.beets_lib.get_album(album_id)
        assert album is not None
        assert album.album == ""
        assert album.year == 0

    async def test_patch_album_no_attributes(self, client: TestClientProtocol):
        """PATCH without any attributes -> 400."""
        response = await client.patch(self._url(self._albums["a"].id), json={})
        assert response.status_code == 400

        data = await response.get_json()
        assert data["type"] == "InvalidUsageError"

    async def test_patch_album_not_found(self, client: TestClientProtocol):
        """PATCH a non-existent album -> 404."""
        response = await client.patch(self._url(999999), json={"album": "Album X"})
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "999999" in data["message"]


class TestDeleteAlbum(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/albums/<album_id>``."""

    _albums: ClassVar[dict[str, BeetsAlbum]] = {}

    @staticmethod
    def _url(album_id: int, delete_files: bool | None = None) -> str:
        """Build the URL for a single album resource."""
        return f"/api_v1/beets/albums/{album_id}" + (
            "?delete_files=true" if delete_files else ""
        )

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib):  # type: ignore
        """Create the albums used by all tests in this class.

        - ``"a"``: album with two items, deleted from the library only
        - ``"b"``: album with one item, deleted together with its file
        """
        a = beets_lib_album(album="Album A", albumartist="Artist One")
        self.beets_lib.add(a)
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 1"))
        self.beets_lib.add(beets_lib_item(album_id=a.id, title="Track 2"))

        b = beets_lib_album(album="Album B", albumartist="Artist Two")
        self.beets_lib.add(b)
        self.beets_lib.add(beets_lib_item(album_id=b.id, title="Track 3"))

        self._albums.update(a=a, b=b)

    async def test_delete_album(self, client: TestClientProtocol):
        """DELETE removes the album and its items from the library."""
        album = self._albums["a"]
        item_ids = [item.id for item in album.items()]
        assert len(item_ids) == 2

        response = await client.delete(self._url(album.id))
        assert response.status_code == 200

        # The response carries the album as it was before the deletion.
        document = SingleAlbumDocument.model_validate(await response.get_json())
        assert document.data.id == str(album.id)
        assert [r.id for r in document.data.relationships] == [
            str(id) for id in item_ids
        ]

        assert self.beets_lib.get_album(album.id) is None
        for item_id in item_ids:
            assert self.beets_lib.get_item(item_id) is None

    async def test_delete_album_delete_files(self, client: TestClientProtocol):
        """DELETE with ``delete_files=true`` also removes the files from disk."""
        album = self._albums["b"]
        item_path = os.fsdecode(album.items()[0].path)
        assert os.path.exists(item_path)

        response = await client.delete(self._url(album.id, delete_files=True))
        assert response.status_code == 200

        assert self.beets_lib.get_album(album.id) is None
        assert not os.path.exists(item_path), "Item file still exists on disk"

    async def test_delete_album_not_found(self, client: TestClientProtocol):
        """DELETE a non-existent album -> 404."""
        response = await client.delete(self._url(999999))
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "999999" in data["message"]
