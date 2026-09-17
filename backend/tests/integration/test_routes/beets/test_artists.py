from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest import mock
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest

from beets_flask.server.routes_next.beets import artists as artists_module
from beets_flask.server.routes_next.beets._types import (
    ArtistSortField,
    Cursor,
    Direction,
    MultiArtistDocument,
    SingleArtistDocument,
    Sort,
)
from tests.conftest import beets_id, beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from quart.typing import TestClientProtocol

    from beets_flask.importer.types import BeetsAlbum, BeetsItem, BeetsLibrary

# The expected artists of the library populated by :func:`_populate`, sorted
# by name (the default sort):
#
# - ``Tool``: 3 items, 2 albums (scalar fallback: multi-value fields empty)
# - ``Pink Floyd``: 2 items, 1 album (scalar fallback)
# - ``Foo``, ``Bar``, ``Baz``: 1 item, 1 album (beets multi-value fields)
# - ``Solo``: 1 item, no album
# - ``Solo Album``: 1 album, no item
_EXPECTED_ARTISTS = ["Bar", "Baz", "Foo", "Pink Floyd", "Solo", "Solo Album", "Tool"]


def _add(
    library: BeetsLibrary, model: BeetsItem | BeetsAlbum, added: int
) -> BeetsItem | BeetsAlbum:
    """Add the model and pin its ``added`` timestamp.

    ``Library.add`` always sets ``added`` to the current time, so it is
    overridden afterwards to keep the test data deterministic.
    """
    library.add(model)
    model.update({"added": added})
    model.store()
    return model


def _populate(library: BeetsLibrary) -> None:
    """Add a small library with single, combined and album-only artists."""
    tool_1 = _add(
        library,
        beets_lib_album(album="Album A", albumartist="Tool"),
        added=2000,
    )
    _add(
        library,
        beets_lib_album(album="Album A2", albumartist="Tool"),
        added=2001,
    )
    for i, added in enumerate((1000, 1001, 1002)):
        _add(
            library,
            beets_lib_item(
                album_id=beets_id(tool_1),
                title=f"Tool {i}",
                artist="Tool",
            ),
            added=added,
        )

    pink = _add(
        library,
        beets_lib_album(album="Album B", albumartist="Pink Floyd"),
        added=2002,
    )
    for i, added in enumerate((1003, 1004)):
        _add(
            library,
            beets_lib_item(
                album_id=beets_id(pink),
                title=f"Pink {i}",
                artist="Pink Floyd",
            ),
            added=added,
        )

    combined = _add(
        library,
        beets_lib_album(
            album="Album C",
            albumartist="Foo; Bar,Baz",
            albumartists=["Foo", "Bar", "Baz"],
        ),
        added=2003,
    )
    _add(
        library,
        beets_lib_item(
            album_id=beets_id(combined),
            title="Foo 0",
            artist="Foo; Bar,Baz",
            artists=["Foo", "Bar", "Baz"],
        ),
        added=1005,
    )

    # Item without an album and album without items: each still counts as
    # an artist, with the missing side's count being zero.
    _add(library, beets_lib_item(title="Solo", artist="Solo"), added=1006)
    _add(
        library,
        beets_lib_album(album="Album D", albumartist="Solo Album"),
        added=2004,
    )


def _ts(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


class TestGetArtist(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/artists/<artist_name>``."""

    @staticmethod
    def _url(artist_name: str) -> str:
        """Build the URL for a single artist resource."""
        return f"/api_v1/beets/artists/{quote(artist_name, safe='')}"

    @pytest.fixture(scope="class", autouse=True)
    def artists(self, setup_beetslib):  # type: ignore
        """Create the artists used by all tests in this class."""
        _populate(self.beets_lib)

    async def test_get_artist(self, client: TestClientProtocol):
        """GET a single artist with its aggregated counts and timestamps."""
        response = await client.get(self._url("Tool"))
        assert response.status_code == 200

        document = SingleArtistDocument.model_validate(await response.get_json())
        assert document.links.self.endswith(self._url("Tool"))
        assert document.data.type == "artist"
        assert document.data.id == "Tool"

        attributes = document.data.attributes
        assert attributes.artist == "Tool"
        assert attributes.album_count == 2
        assert attributes.item_count == 3
        assert attributes.first_item_added == _ts(1000)
        assert attributes.last_item_added == _ts(1002)
        assert attributes.first_album_added == _ts(2000)
        assert attributes.last_album_added == _ts(2001)

    @pytest.mark.parametrize("artist_name", ["Foo", "Bar", "Baz"])
    async def test_get_split_artist(self, client: TestClientProtocol, artist_name: str):
        """GET a single artist that only exists as part of a combined name."""
        response = await client.get(self._url(artist_name))
        assert response.status_code == 200

        document = SingleArtistDocument.model_validate(await response.get_json())
        assert document.data.id == artist_name
        assert document.data.attributes.album_count == 1
        assert document.data.attributes.item_count == 1

    async def test_get_artist_without_items(self, client: TestClientProtocol):
        """An album-only artist has ``item_count`` zero and no item timestamps."""
        response = await client.get(self._url("Solo Album"))
        assert response.status_code == 200

        attributes = SingleArtistDocument.model_validate(
            await response.get_json()
        ).data.attributes
        assert attributes.album_count == 1
        assert attributes.item_count == 0
        assert attributes.first_item_added is None
        assert attributes.last_item_added is None
        assert attributes.first_album_added == _ts(2004)

    async def test_get_artist_without_albums(self, client: TestClientProtocol):
        """An item-only artist has ``album_count`` zero and no album timestamps."""
        response = await client.get(self._url("Solo"))
        assert response.status_code == 200

        attributes = SingleArtistDocument.model_validate(
            await response.get_json()
        ).data.attributes
        assert attributes.album_count == 0
        assert attributes.item_count == 1
        assert attributes.first_item_added == _ts(1006)
        assert attributes.first_album_added is None
        assert attributes.last_album_added is None

    async def test_get_artist_not_found(self, client: TestClientProtocol):
        """GET a non-existent artist -> 404."""
        response = await client.get(self._url("No Such Artist"))
        assert response.status_code == 404

        data = await response.get_json()
        assert data["type"] == "NotFoundError"
        assert "No Such Artist" in data["message"]

    async def test_multi_value_takes_precedence(self, client: TestClientProtocol):
        """When present, the multi-value field wins over the scalar field."""
        response = await client.get(self._url("Foo; Bar,Baz"))
        assert response.status_code == 404

    async def test_scalar_separators_split(self, client: TestClientProtocol):
        """The configured separators split scalar artist names."""
        # Added after the exact-count tests: they would see this item too.
        self.beets_lib.add(beets_lib_item(title="Split", artist="A, B"))

        for name in ("A", "B"):
            response = await client.get(self._url(name))
            assert response.status_code == 200
            document = SingleArtistDocument.model_validate(await response.get_json())
            assert document.data.id == name
            assert document.data.attributes.item_count == 1

        # The unsplit combined name is not an artist.
        response = await client.get(self._url("A, B"))
        assert response.status_code == 404

    async def test_separators_can_be_disabled(self, client: TestClientProtocol):
        """An empty separator list keeps the scalar name a single artist."""
        self.beets_lib.add(beets_lib_item(title="Whole", artist="C & D"))

        with mock.patch(
            "beets_flask.server.routes_next.beets.artists.artist_separators",
            lambda: [],
        ):
            response = await client.get(self._url("C & D"))
            assert response.status_code == 200
            document = SingleArtistDocument.model_validate(await response.get_json())

            # Without separators the parts are not artists of their own.
            response = await client.get(self._url("C"))
            assert response.status_code == 404

        assert document.data.id == "C & D"
        assert document.data.attributes.item_count == 1


class BulkGetArtistsBase(IsolatedBeetsLibraryMixin):
    """Shared helpers of the bulk artist endpoint tests."""

    @staticmethod
    def _url(**params: object) -> str:
        """Build the URL of the bulk artists endpoint from query params."""
        query = urlencode(params, doseq=True)
        return "/api_v1/beets/artists/" + (f"?{query}" if query else "")

    @staticmethod
    def _names(document: MultiArtistDocument) -> list[str]:
        return [resource.attributes.artist for resource in document.data]

    @staticmethod
    def _next_url(document: MultiArtistDocument) -> str | None:
        """Path+query of the typed ``links.next``, or ``None`` on the last page."""
        if document.links is None or document.links.next is None:
            return None
        url = urlsplit(document.links.next)
        return url.path + "?" + url.query

    @staticmethod
    def _cursor_of(document: MultiArtistDocument) -> str:
        """The ``cursor`` query param of the typed ``links.next``."""
        assert document.links is not None and document.links.next is not None
        return parse_qs(urlsplit(document.links.next).query)["cursor"][0]

    async def _walk(
        self, client: TestClientProtocol, expected_total: int, **params: object
    ) -> AsyncGenerator[MultiArtistDocument, None]:
        """Walk ``links.next`` until exhausted, yielding each page's document."""
        url = self._url(**params)
        while url is not None:
            response = await client.get(url)
            assert response.status_code == 200
            document = MultiArtistDocument.model_validate(await response.get_json())
            assert document.meta is not None and document.meta.total == expected_total
            assert document.links is not None and document.links.self

            yield document
            url = self._next_url(document)


class TestGetArtists(BulkGetArtistsBase):
    """Tests for ``GET /api_v1/beets/artists/`` (bulk)."""

    @pytest.fixture(scope="class", autouse=True)
    def artists(self, setup_beetslib):  # type: ignore
        """Create the artists used by all tests in this class."""
        _populate(self.beets_lib)

    async def test_get_artists(self, client: TestClientProtocol):
        """A bare request returns all artists, sorted by name."""
        response = await client.get(self._url())
        assert response.status_code == 200

        document = MultiArtistDocument.model_validate(await response.get_json())
        assert document.meta is not None and document.meta.total == len(
            _EXPECTED_ARTISTS
        )
        assert self._names(document) == _EXPECTED_ARTISTS
        assert document.links is not None and document.links.next is None

    async def test_get_artists_sort(self, client: TestClientProtocol):
        """``sort`` orders by the aggregated item count (descending).

        Ties are broken by the artist name, descending as well.
        """
        response = await client.get(self._url(sort="-item_count"))
        assert response.status_code == 200

        document = MultiArtistDocument.model_validate(await response.get_json())
        assert self._names(document) == [
            "Tool",
            "Pink Floyd",
            "Solo",
            "Foo",
            "Baz",
            "Bar",
            "Solo Album",
        ]

    @pytest.mark.parametrize("sort", ["artist", "-album_count"])
    async def test_get_artists_walk(self, client: TestClientProtocol, sort: str):
        """Walking ``links.next`` yields every artist exactly once, in sort order."""
        names = [
            name
            async for document in self._walk(
                client, expected_total=len(_EXPECTED_ARTISTS), sort=sort, limit=2
            )
            for name in self._names(document)
        ]
        if sort == "artist":
            assert names == _EXPECTED_ARTISTS
        else:
            # album_count descending, ties broken by artist name (descending)
            assert names == [
                "Tool",
                "Solo Album",
                "Pink Floyd",
                "Foo",
                "Baz",
                "Bar",
                "Solo",
            ]

    @pytest.mark.parametrize(
        "params",
        [
            {"sort": "bogus"},
            {"limit": 0},
            {"limit": 1001},
            {"cursor": "zznotbase64"},
        ],
        ids=["bad_sort", "limit_zero", "limit_too_big", "bad_cursor"],
    )
    async def test_get_artists_invalid_params(
        self, client: TestClientProtocol, params: dict[str, object]
    ):
        """Malformed query parameters -> 400."""
        response = await client.get(self._url(**params))
        assert response.status_code == 400

    async def test_get_artists_cursor_exclusive(self, client: TestClientProtocol):
        """A cursor cannot be combined with ``sort``."""
        response = await client.get(self._url(limit=1))
        assert response.status_code == 200
        document = MultiArtistDocument.model_validate(await response.get_json())
        cursor = self._cursor_of(document)

        response = await client.get(self._url(cursor=cursor, sort="artist"))
        assert response.status_code == 400

    async def test_get_artists_unknown_cursor_field(self, client: TestClientProtocol):
        """A cursor token with a forged sort field -> 400."""
        # Re-encode a valid cursor with a sort field outside ArtistSortField.
        token = Cursor[Sort[ArtistSortField]](
            sort=Sort[ArtistSortField](
                field=ArtistSortField.ARTIST, direction=Direction.ASC
            )
        ).to_string()
        data = json.loads(Cursor._b64decode(token))
        data["sort"]["field"] = "path"
        forged = Cursor._b64encode(json.dumps(data, separators=(",", ":")).encode())

        response = await client.get(self._url(cursor=forged))
        assert response.status_code == 400


class TestGetArtistsEmpty(IsolatedBeetsLibraryMixin):
    """The artist endpoints on an empty library (zero-size numpy arrays)."""

    async def test_get_artists_empty(self, client: TestClientProtocol):
        """An empty library yields an empty artist list, not an error."""
        response = await client.get("/api_v1/beets/artists/")
        assert response.status_code == 200

        document = MultiArtistDocument.model_validate(await response.get_json())
        assert document.data == []
        assert document.meta is not None and document.meta.total == 0

    async def test_get_artist_empty(self, client: TestClientProtocol):
        """No artist exists in an empty library -> 404."""
        response = await client.get("/api_v1/beets/artists/No One")
        assert response.status_code == 404


class TestGetArtistsCache(BulkGetArtistsBase):
    """The server-side aggregation cache of the bulk artist endpoint."""

    @pytest.fixture(scope="class", autouse=True)
    def artists(self, setup_beetslib):  # type: ignore
        _populate(self.beets_lib)

    async def test_get_artists_is_cached(self, client: TestClientProtocol):
        """Consecutive bulk requests reuse the cached aggregation."""
        artists_module._all_artists.cache_clear()
        before = artists_module._all_artists.cache_info()

        for _ in range(2):
            response = await client.get(self._url())
            assert response.status_code == 200

        after = artists_module._all_artists.cache_info()
        assert after.misses - before.misses == 1
        assert after.hits - before.hits == 1

    async def test_get_artists_cache_invalidated(self, client: TestClientProtocol):
        """A write to the library invalidates the cached aggregation."""
        artists_module._all_artists.cache_clear()
        before = artists_module._all_artists.cache_info()

        response = await client.get(self._url())
        document = MultiArtistDocument.model_validate(await response.get_json())
        assert "New Artist" not in self._names(document)

        self.beets_lib.add(beets_lib_item(title="New", artist="New Artist"))

        response = await client.get(self._url())
        document = MultiArtistDocument.model_validate(await response.get_json())
        assert "New Artist" in self._names(document)
        assert artists_module._all_artists.cache_info().misses - before.misses == 2
