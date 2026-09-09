from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

import pytest

from beets_flask.server.routes_next.beets._types import SingleItemDocument
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from quart.typing import TestClientProtocol

    from beets_flask.importer.types import BeetsAlbum, BeetsItem


class TestGetItem(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/items/<item_id>``."""

    _items: ClassVar[dict[str, BeetsItem]] = {}

    @staticmethod
    def _url(item_id: int) -> str:
        """Build the URL for a single item resource."""
        return f"/api_v1/beets/items/{item_id}"

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create the items used by all tests in this class."""
        item = beets_lib_item(title="Item A", artist="Artist One")
        self.beets_lib.add(item)
        self._items["a"] = item

    async def test_get_item(self, client: TestClientProtocol):
        """GET a single item."""
        item = self.beets_lib.get_item(self._items["a"].id)
        assert item is not None

        response = await client.get(self._url(item.id))
        assert response.status_code == 200

        SingleItemDocument.model_validate(await response.get_json())

    async def test_get_item_not_found(self, client: TestClientProtocol):
        """GET a non-existent item -> 404."""
        response = await client.get(self._url(999999))
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "999999" in data["message"], "Error message does not name the item id"


class TestPatchItem(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/items/<item_id>``."""

    _items: ClassVar[dict[str, BeetsItem]] = {}

    @staticmethod
    def _url(item_id: int) -> str:
        """Build the URL for a single item resource."""
        return f"/api_v1/beets/items/{item_id}"

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create the items used by all tests in this class.

        - ``"a"``: item whose attributes are fully updated
        - ``"b"``: item whose ``title`` is updated
        - ``"c"``: item whose ``title`` is cleared with an explicit ``null``
        """
        a = beets_lib_item(title="Item A", artist="Artist One")
        self.beets_lib.add(a)

        b = beets_lib_item(title="Item B", artist="Artist Two")
        self.beets_lib.add(b)

        c = beets_lib_item(title="Item C", artist="Artist Three")
        self.beets_lib.add(c)

        self._items.update(a=a, b=b, c=c)

    async def test_patch_item(self, client: TestClientProtocol):
        """PATCH updates the given attributes and persists them in the library."""
        item_id = self._items["a"].id
        updates = {"title": "Item A Updated", "artist": "Artist One Updated"}

        response = await client.patch(self._url(item_id), json=updates)
        assert response.status_code == 200

        document = SingleItemDocument.model_validate(await response.get_json())
        assert document.data.id == str(item_id)
        assert document.data.attributes.model_dump() == updates

        item = self.beets_lib.get_item(item_id)
        assert item is not None
        assert item.title == updates["title"]
        assert item.artist == updates["artist"]

    async def test_patch_item_partial(self, client: TestClientProtocol):
        """PATCH only the given attributes; absent ones are left unchanged."""
        item_id = self._items["b"].id

        response = await client.patch(self._url(item_id), json={"title": "Item B2"})
        assert response.status_code == 200

        document = SingleItemDocument.model_validate(await response.get_json())
        attributes = document.data.attributes.model_dump()
        assert attributes["title"] == "Item B2"
        assert attributes["artist"] == "Artist Two", "Unpatched attribute was changed"

        item = self.beets_lib.get_item(item_id)
        assert item is not None
        assert item.title == "Item B2"
        assert item.artist == "Artist Two"

    async def test_patch_item_null_clears_attribute(self, client: TestClientProtocol):
        """PATCH with an explicit ``null`` clears the attribute.

        Beets fixed fields cannot hold NULL: ``None`` is normalized to the
        field's empty value on store (``''`` for strings, ``0`` for numbers).
        """
        item_id = self._items["c"].id

        response = await client.patch(self._url(item_id), json={"title": None})
        assert response.status_code == 200

        document = SingleItemDocument.model_validate(await response.get_json())
        attributes = document.data.attributes.model_dump()

        # The null value normilization is a bit weird!
        # We might need to change this in beets!
        assert attributes["title"] == ""
        assert attributes["artist"] == "Artist Three", "Unpatched attribute was changed"

        item = self.beets_lib.get_item(item_id)
        assert item is not None
        assert item.title == ""

    async def test_patch_item_no_attributes(self, client: TestClientProtocol):
        """PATCH without any attributes -> 400."""
        response = await client.patch(self._url(self._items["a"].id), json={})
        assert response.status_code == 400

        data = await response.get_json()
        assert data["type"] == "InvalidUsageError"

    async def test_patch_item_not_found(self, client: TestClientProtocol):
        """PATCH a non-existent item -> 404."""
        response = await client.patch(self._url(999999), json={"title": "Item X"})
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "999999" in data["message"], "Error message does not name the item id"


class TestDeleteItem(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/items/<item_id>``."""

    _items: ClassVar[dict[str, BeetsItem]] = {}
    _albums: ClassVar[dict[str, BeetsAlbum]] = {}

    @staticmethod
    def _url(item_id: int, delete_file: bool | None = None) -> str:
        """Build the URL for a single item resource."""
        return f"/api_v1/beets/items/{item_id}" + (
            "?delete_file=true" if delete_file else ""
        )

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create the items used by all tests in this class.

        - ``"a"``: standalone item, deleted from the library only
        - ``"b"``: standalone item, deleted together with its file
        - ``"c"``: the only item of its album, deleted with ``with_album``
        """
        a = beets_lib_item(title="Item A", artist="Artist One")
        self.beets_lib.add(a)

        b = beets_lib_item(title="Item B", artist="Artist Two")
        self.beets_lib.add(b)

        album = beets_lib_album(album="Album Solo", albumartist="Solo Artist")
        self.beets_lib.add(album)
        c = beets_lib_item(album_id=album.id, title="Solo Track")
        self.beets_lib.add(c)

        self._items.update(a=a, b=b, c=c)
        self._albums["solo"] = album

    async def test_delete_item(self, client: TestClientProtocol):
        """DELETE removes the item from the library."""
        item_id = self._items["a"].id

        response = await client.delete(self._url(item_id))
        assert response.status_code == 200

        # The response carries the item as it was before the deletion.
        document = SingleItemDocument.model_validate(await response.get_json())
        assert document.data.id == str(item_id)
        assert document.data.attributes.title == "Item A"

        assert self.beets_lib.get_item(item_id) is None

    async def test_delete_item_removes_album_of_last_item(
        self, client: TestClientProtocol
    ):
        """DELETE the last item of an album removes the album as well."""
        album = self._albums["solo"]
        item_id = self._items["c"].id

        response = await client.delete(self._url(item_id))
        assert response.status_code == 200

        assert self.beets_lib.get_item(item_id) is None
        assert self.beets_lib.get_album(album.id) is None, "Album was not removed"

    async def test_delete_item_delete_file(self, client: TestClientProtocol):
        """DELETE with ``delete_file=true`` also removes the file from disk."""
        item = self._items["b"]
        item_path = os.fsdecode(item.path)
        assert os.path.exists(item_path)

        response = await client.delete(self._url(item.id, delete_file=True))
        assert response.status_code == 200

        assert self.beets_lib.get_item(item.id) is None
        assert not os.path.exists(item_path), "Item file still exists on disk"

    async def test_delete_item_not_found(self, client: TestClientProtocol):
        """DELETE a non-existent item -> 404."""
        response = await client.delete(self._url(999999))
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "999999" in data["message"]
