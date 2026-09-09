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
