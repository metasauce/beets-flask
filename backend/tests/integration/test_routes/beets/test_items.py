"""Tests for the new beets items API endpoints.

Covers the implemented endpoints of ``beets_flask/server/routes/beets/items.py``:

- ``GET /api_v1/beets/items/<item_id>``
- ``PATCH /api_v1/beets/items/<item_id>``
- ``DELETE /api_v1/beets/items/<item_id>``

The bulk endpoints (``GET/PATCH/DELETE /api_v1/beets/items/``) are not
implemented yet and are only tested to return 501.
"""

import os
from pathlib import Path

import pytest
from beets.library import Item
from quart.typing import TestClientProtocol as Client

from beets_flask.config import get_config
from tests.conftest import beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin


def _item_url(item_id: int) -> str:
    """Build the URL for a single item resource."""
    return f"/api_v1/beets/items/{item_id}"


def _item_file(name: str) -> Path:
    """Path of a dedicated audio file for a test item."""
    return Path(os.environ["HOME"]) / "audio" / name


def _assert_item_document(data: dict, item: Item) -> None:
    """Assert the JSON:API-ish shape of a single-item document."""
    assert data["data"]["type"] == "item"
    assert data["data"]["id"] == str(item.id)
    assert data["data"]["attributes"] == {"title": item.title}


# ----------------------------------- Get ----------------------------------- #


class TestGetItem(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/items/<item_id>``."""

    _items: dict[str, Item] = {}

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create the items used by all tests in this class."""
        item = beets_lib_item(title="Item A", artist="Artist One")
        self.beets_lib.add(item)
        self._items["a"] = item

    async def test_get_item(self, client: Client):
        """GET a single item."""
        item = self.beets_lib.get_item(self._items["a"].id)
        assert item is not None

        response = await client.get(_item_url(item.id))
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        _assert_item_document(data, item)

    async def test_get_item_not_found(self, client: Client):
        """GET a non-existent item -> 404."""
        response = await client.get(_item_url(999999))
        data = await response.get_json()

        assert response.status_code == 404, "Response status code is not 404"
        assert data["type"] == "NotFoundException"
        assert "999999" in data["message"], "Error message does not name the item id"


# ---------------------------------- Patch ---------------------------------- #


class TestPatchItem(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/items/<item_id>``."""

    _items: dict[str, Item] = {}

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create the items used by all tests in this class.

        - ``"a"``: modified by the title test
        - ``"b"``: never modified (noop and readonly tests)
        """
        a = beets_lib_item(title="Item A", artist="Artist One")
        self.beets_lib.add(a)
        b = beets_lib_item(title="Item B", artist="Artist Two")
        self.beets_lib.add(b)
        self._items.update(a=a, b=b)

    async def test_patch_item_title(self, client: Client):
        """PATCH the item title."""
        item = self.beets_lib.get_item(self._items["a"].id)
        assert item is not None
        new_title = "Updated Item Title"

        response = await client.patch(_item_url(item.id), json={"title": new_title})
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["attributes"]["title"] == new_title

        # The change must be persisted and the response must match the new state
        stored = self.beets_lib.get_item(item.id)
        assert stored is not None
        assert stored.title == new_title, "Title was not updated in the beets library"
        _assert_item_document(data, stored)

    async def test_patch_item_not_found(self, client: Client):
        """PATCH a non-existent item -> 404."""
        response = await client.patch(
            _item_url(999999), json={"title": "Does Not Matter"}
        )
        data = await response.get_json()

        assert response.status_code == 404, "Response status code is not 404"
        assert data["type"] == "NotFoundException"

    async def test_patch_item_empty_body_is_noop(self, client: Client):
        """PATCH with an empty body must not change anything."""
        item = self.beets_lib.get_item(self._items["b"].id)
        assert item is not None

        response = await client.patch(_item_url(item.id), json={})
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["attributes"]["title"] == item.title

        stored = self.beets_lib.get_item(item.id)
        assert stored is not None
        assert stored.title == item.title, "Item was modified by an empty patch"

    async def test_patch_item_readonly(self, client: Client):
        """PATCH must fail and not modify the item when the library is read-only."""
        item = self.beets_lib.get_item(self._items["b"].id)
        assert item is not None

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.patch(
                _item_url(item.id), json={"title": "Should Not Apply"}
            )
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

        stored = self.beets_lib.get_item(item.id)
        assert stored is not None
        assert stored.title == item.title, (
            "Item was modified even though the library is read-only"
        )


# ---------------------------------- Delete --------------------------------- #


class TestDeleteItem(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/items/<item_id>``."""

    _items: dict[str, Item] = {}

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create the items used by all tests in this class.

        - ``"a"``: deleted by the delete test
        - ``"b"``: never deleted (readonly test)
        """
        a = beets_lib_item(title="Item A", artist="Artist One")
        self.beets_lib.add(a)
        b = beets_lib_item(title="Item B", artist="Artist Two")
        self.beets_lib.add(b)
        self._items.update(a=a, b=b)

    async def test_delete_item(self, client: Client):
        """DELETE a single item, keeping its file on disk."""
        item = self.beets_lib.get_item(self._items["a"].id)
        assert item is not None

        response = await client.delete(_item_url(item.id))
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["id"] == str(item.id)
        assert data["data"]["attributes"] == {"title": item.title}

        assert self.beets_lib.get_item(item.id) is None, (
            "Item was not removed from the beets library"
        )

    async def test_delete_item_not_found(self, client: Client):
        """DELETE a non-existent item -> 404."""
        response = await client.delete(_item_url(999999))
        data = await response.get_json()

        assert response.status_code == 404, "Response status code is not 404"
        assert data["type"] == "NotFoundException"

    async def test_delete_item_readonly(self, client: Client):
        """DELETE must fail and not modify the item when the library is read-only."""
        item = self.beets_lib.get_item(self._items["b"].id)
        assert item is not None

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.delete(_item_url(item.id))
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

        assert self.beets_lib.get_item(item.id) is not None, (
            "Item was removed even though the library is read-only"
        )


class TestDeleteItemFile(IsolatedBeetsLibraryMixin):
    """Tests for the ``delete_file`` parameter of the item delete endpoint."""

    _items: dict[str, Item] = {}

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create items with dedicated files on disk."""
        for key, file_name in (
            ("keep", "delete_keep.mp3"),
            ("delete", "delete_remove.mp3"),
            ("keep_false", "delete_false.mp3"),
        ):
            item = beets_lib_item(title=f"File Item {key}")
            self.beets_lib.add(item)
            path = _item_file(file_name)
            path.write_bytes(b"fake mp3")
            item.path = str(path).encode()
            item.store()
            self._items[key] = item

    async def test_delete_item_keeps_file_by_default(self, client: Client):
        """DELETE without ``delete_file`` keeps the file on disk."""
        item = self._items["keep"]
        path = _item_file("delete_keep.mp3")
        assert path.exists()

        response = await client.delete(_item_url(item.id))

        assert response.status_code == 200, "Response status code is not 200"
        assert path.exists(), "File was deleted although delete_file was not set"

    async def test_delete_item_with_file(self, client: Client):
        """DELETE with ``delete_file=true`` also removes the file from disk."""
        item = self._items["delete"]
        path = _item_file("delete_remove.mp3")
        assert path.exists()

        response = await client.delete(_item_url(item.id) + "?delete_file=true")

        assert response.status_code == 200, "Response status code is not 200"
        assert not path.exists(), "File was not deleted although delete_file=true"

    async def test_delete_item_delete_file_false(self, client: Client):
        """DELETE with ``delete_file=false`` keeps the file on disk."""
        item = self._items["keep_false"]
        path = _item_file("delete_false.mp3")
        assert path.exists()

        response = await client.delete(_item_url(item.id) + "?delete_file=false")

        assert response.status_code == 200, "Response status code is not 200"
        assert path.exists(), "File was deleted although delete_file=false"


# -------------------------------- Not implemented ------------------------------- #


class TestBulkItemsNotImplemented(IsolatedBeetsLibraryMixin):
    """Tests for the not-yet-implemented bulk items endpoints."""

    @pytest.mark.parametrize("method", ["get", "patch", "delete"])
    async def test_bulk_items_not_implemented(self, client: Client, method: str):
        """The bulk items endpoints are not implemented yet -> 501."""
        response = await getattr(client, method)("/api_v1/beets/items/", json={})
        data = await response.get_json()

        assert response.status_code == 501, "Response status code is not 501"
        assert data["type"] == "NotImplementedException"
