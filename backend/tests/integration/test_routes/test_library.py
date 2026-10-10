"""
Currently still requires a beets library with some content in
the default location of the user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from quart.typing import TestClientProtocol as Client

# ---------------------------------------------------------------------------- #
#                                   Test art                                   #
# ---------------------------------------------------------------------------- #


@pytest.mark.skip("Test is skipped because it requires a beets library with art. TODO")
class TestArtEndpoint(IsolatedBeetsLibraryMixin):
    """Test class for the Art endpoint in the API.

    This class contains tests for retrieving art for items and albums
    from the beets library via the API.
    """

    @pytest.fixture(autouse=True)
    def items(self):  # type: ignore
        """Fixture to add items to the beets library before running tests."""
        self.beets_lib.add(beets_lib_item(artist="Basstripper", album="Bass"))
        self.beets_lib.add(beets_lib_album(artist="Beta", album="Alpha"))

    async def test_get_art(
        self,
        client: Client,
    ):
        """Test the GET request to retrieve art for an item and an album.

        Asserts:
            - The response status code is 200 for each item and album.
        """

        items = self.beets_lib.items()
        for item in items:
            response = await client.get(f"/api_v1/library/item/{item.id}/art")
            data = await response.get_json()
            print(data)
            assert response.status_code == 200

        albums = self.beets_lib.albums()

        for album in albums:
            response = await client.get(f"/api_v1/library/album/{album.id}/art")
            data = await response.get_json()
            assert response.status_code == 200
