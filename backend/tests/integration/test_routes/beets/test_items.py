from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from beets_flask.server.routes_next.beets._types import SingleItemDocument
from tests.conftest import beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from quart.typing import TestClientProtocol

    from beets_flask.importer.types import BeetsItem


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
