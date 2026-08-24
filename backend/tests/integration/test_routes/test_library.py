"""
Currently still requires a beets library with some content in
the default location of the user.
"""

from unittest import mock
from urllib.parse import quote_plus

import pytest
from beets.library import Album
from quart.typing import TestClientProtocol as Client

from beets_flask.config import get_config
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

# ----------------------------------- Artist --------------------------------- #


class TestArtistsEndpoint(IsolatedBeetsLibraryMixin):
    """Test class for the Albums endpoint in the API.

    This class contains tests for retrieving albums and individual album details
    from the beets library via the API.
    """

    artists = ["Basstripper", "Beta", "Foo; Bar,Baz"]
    expected_artists = [
        "Basstripper",
        "Beta",
        "Foo",
        "Bar",
        "Baz",
    ]  # Artists should be split by semicolon

    _albums: list[Album] = []

    @pytest.fixture(autouse=True)
    def albums(self):  # type: ignore
        """Fixture to add albums to the beets library before running tests."""
        if len(self._albums) == len(self.artists):
            # If albums are already added, skip adding them again
            return

        for artist in self.artists:
            a = beets_lib_album(albumartist=artist)
            self.beets_lib.add(a)
            self.beets_lib.add(beets_lib_item(album_id=a.id, artist=artist))
            self._albums.append(a)

    async def test_get_artists(self, client: Client):
        """Test the GET request to retrieve all albums by a specific artist.

        Asserts:
            - The response status code is 200 for each artist.
            - The returned data artist matches the requested artist.
        """

        response = await client.get("/api_v1/library/artists/")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"

        # Should return one entry for each artist, additionally seperators
        # in artist names should also be handled correctly
        for d in data:
            assert d["artist"] in self.expected_artists, (
                f"Artist {d['artist']} not in expected artists {self.expected_artists}"
            )

    async def test_get_single_artist(
        self,
        client: Client,
    ):
        """Test the GET request to retrieve all albums by a specific artist.

        Asserts:
            - The response status code is 200 for each artist.
            - The returned data artist matches the requested artist.
        """
        for artist in self.expected_artists:
            # Encode the artist name to handle special characters
            encoded_artist = quote_plus(artist)
            response = await client.get(f"/api_v1/library/artists/{encoded_artist}")
            data = await response.get_json()
            assert "artist" in data, "Artist key is not in the response"
            assert data["artist"] == artist, "Artist does not match requested artist"

    async def test_separator(self, client: Client):
        """Test the GET request to retrieve a specific artist with a separator in the name.

        Should return the artist even if the name contains a separator.
        """
        # Test with a separator in the artist name
        response = await client.get("/api_v1/library/artists/Foo; Bar,Baz")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        assert data["artist"] == "Foo; Bar,Baz", (
            "Data artist does not match requested artist with separator"
        )

        # Order of the artists should not matter, so we can also test with a different order
        response = await client.get("/api_v1/library/artists/Foo; Baz")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        assert data["artist"] == "Foo; Baz", (
            "Data artist does not match requested artist with separator"
        )

        # Should not be found if one of the joined artists is not in the library
        response = await client.get("/api_v1/library/artists/Foo; Bar, NotInLibrary")
        assert response.status_code == 404, "Response status code is not 404"

    async def test_no_separators(self, client: Client):
        # Validate that the logic works if no separators are defined

        config = get_config()
        config.reload()
        config.data.gui.library.artist_separators = []

        # Mock artist_seperators
        with mock.patch(
            "beets_flask.server.routes.library.artists.artist_separators",
            lambda: [],
        ):
            response = await client.get("/api_v1/library/artists/Foo; Bar")
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["artist"] == "Foo; Bar,Baz", (
                "Data artist does not match requested artist without separators"
            )


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
