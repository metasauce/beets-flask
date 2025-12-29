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

    async def test_get_artist(self, client: Client):
        """Test the GET request to retrieve a specific artist by its ID.

        Asserts:
            - The response status code is 200 for each artist.
            - The returned data ID matches the requested artist ID.
        """

        for artist in self.artists:
            response = await client.get(f"/api_v1/library/artist/{artist}/albums")
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            # We added one album and one item for each artist
            assert len(data) == 1, "Data length is not 1"
            assert data[0]["albumartist"] == artist, "Data artist does not match artist"

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


# ----------------------------------- album ---------------------------------- #


class TestAlbumEndpoints(IsolatedBeetsLibraryMixin):
    """Test class for the Albums endpoint in the API.

    This class contains tests for retrieving albums and individual album details
    from the beets library via the API.
    """

    @pytest.fixture(autouse=True)
    def albums(self):  # type: ignore
        """Fixture to add albums to the beets library before running tests."""
        a = beets_lib_album(artist="Basstripper", album="Bass")
        self.beets_lib.add(a)
        self.beets_lib.add(beets_lib_item(artist="Beta", album_id=a.id))

    @pytest.mark.asyncio
    async def test_get_album(
        self,
        client: Client,
    ):
        """Test the GET request to retrieve a specific album by its ID.

        Asserts:
            - The response status code is 200 for each album.
            - The returned data ID matches the requested album ID.
        """
        albums = self.beets_lib.albums()
        for album in albums:
            response = await client.get(f"/api_v1/library/album/{album.id}")
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["id"] == album.id, "Data id does not match album id"


class TestAlbumsPagination(IsolatedBeetsLibraryMixin):
    """Test if pagination of albums works as expected"""

    @pytest.fixture(autouse=True)
    def albums(self):  # type: ignore
        """Fixture to add albums to the beets library before running tests."""
        nAlbums = 100
        if len(self.beets_lib.albums()) == 0:
            for i in range(nAlbums):
                artist = "Even" if i % 2 == 0 else f"Odd"
                a = beets_lib_album(albumartist=f"{artist}", album=f"Album {i}")
                self.beets_lib.add(a)
                self.beets_lib.add(beets_lib_item(artist=f"{artist}", album_id=a.id))

        assert len(self.beets_lib.albums()) == nAlbums

    async def test_get_albums(self, client: Client):
        """Test the GET request to retrieve all albums with pagination.

        Asserts:
            - The response status code is 200.
            - The returned data contains the expected number of albums.
            - The next cursor is provided for pagination.
        """
        response = await client.get("/api_v1/library/albums/?n_items=10")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        assert "albums" in data, "Items are not provided in the response"
        assert len(data["albums"]) == 10, "Data length is not 10"
        assert "next" in data, "Next cursor is not provided"
        assert "total" in data, "Total count is not provided"
        assert data["total"] == 100, "Total count does not match expected value"

    async def test_iter_cusor(self, client: Client):
        """Test the GET request to retrieve all albums with pagination using cursor.

        Asserts:
            - The response status code is 200.
            - The returned data contains the expected number of albums.
            - The next cursor is provided for pagination.
        """

        next_url: str | None = "/api_v1/library/albums/?n_items=10"
        albums = []
        total_albums = len(self.beets_lib.albums())
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert "albums" in data, "Items are not provided in the response"
            assert "next" in data, "Next cursor is not provided"
            assert data["total"] == total_albums, (
                "Total count does not match expected value"
            )
            albums.extend(data["albums"])
            next_url = data["next"] if "next" in data else None

        assert len(albums) == len(self.beets_lib.albums()), (
            "Total number of albums does not match expected value"
        )

    @pytest.mark.parametrize(
        "order_by, order_dir",
        [
            ("albumartist", "ASC"),
            ("albumartist", "DESC"),
        ],
    )
    async def test_ordering(self, client: Client, order_by, order_dir):
        """Test the GET request to retrieve all albums with ordering.

        Asserts:
            - The response status code is 200.
            - The returned data contains the expected number of albums.
            - The albums are ordered by artist and album name.
        """
        next_url: str | None = (
            f"/api_v1/library/albums/?n_items=10&order_by={order_by}&order_dir={order_dir}"
        )

        albums = []
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert "albums" in data, "Items are not provided in the response"
            assert "next" in data, "Next cursor is not provided"
            albums.extend(data["albums"])
            next_url = data["next"] if "next" in data else None
        assert len(albums) == len(self.beets_lib.albums()), (
            "Total number of albums does not match expected value"
        )

        # Assert ordering
        for i in range(1, len(albums)):
            if order_dir == "ASC":
                assert albums[i][order_by] >= albums[i - 1][order_by], (
                    f"Albums are not ordered by {order_by} in ascending order"
                )
            else:
                assert albums[i][order_by] <= albums[i - 1][order_by], (
                    f"Albums are not ordered by {order_by} in descending order"
                )

    async def test_with_query(
        self,
        client: Client,
    ):
        """Test the GET request to retrieve all albums with a query.

        Asserts:
            - The response status code is 200.
            - The returned data contains the expected number of albums.
            - The albums match the query.
        """
        response = await client.get(f"/api_v1/library/albums/Even?n_items=100")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        assert "albums" in data, "Items are not provided in the response"
        assert len(data["albums"]) == 50


# ----------------------------------- Items ---------------------------------- #


class TestItemEndpoint(IsolatedBeetsLibraryMixin):
    """Test class for the Items endpoint in the API.

    This class contains tests for retrieving items and individual item details
    from the beets library via the API.
    """

    @pytest.fixture(autouse=True)
    def items(self):  # type: ignore
        """Fixture to add items to the beets library before running tests."""
        self.beets_lib.add(beets_lib_item(artist="Basstripper", album="Bass"))
        self.beets_lib.add(beets_lib_item(artist="Beta", album="Alpha"))

    @pytest.mark.asyncio
    async def test_get_item(self, client: Client):
        """Test the GET request to retrieve a specific item by its ID.

        Asserts:
            - The response status code is 200 for each item.
            - The returned data ID matches the requested item ID.
        """
        items = self.beets_lib.items()
        for item in items:
            response = await client.get(f"/api_v1/library/item/{item.id}")
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["id"] == item.id, "Data id does not match item id"


class TestItemsPagination(IsolatedBeetsLibraryMixin):
    """Test if pagination of items works as expected"""

    @pytest.fixture(autouse=True)
    def items(self):  # type: ignore
        """Fixture to add items to the beets library before running tests."""
        nItems = 100
        if len(self.beets_lib.items()) == 0:
            for i in range(nItems):
                artist = "Even" if i % 2 == 0 else f"Odd"
                self.beets_lib.add(
                    beets_lib_item(artist=f"{artist}", album=f"Album {i}")
                )

        assert len(self.beets_lib.items()) == nItems

    async def test_get_items(self, client: Client):
        """Test the GET request to retrieve all items with pagination.

        Asserts:
            - The response status code is 200.
            - The returned data contains the expected number of items.
            - The next cursor is provided for pagination.
        """
        response = await client.get("/api_v1/library/items/?n_items=10")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        assert "items" in data, "Items are not provided in the response"
        assert len(data["items"]) == 10, "Data length is not 10"
        assert "next" in data, "Next cursor is not provided"
        assert "total" in data, "Total count is not provided"
        assert data["total"] == 100, "Total count does not match expected value"


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
