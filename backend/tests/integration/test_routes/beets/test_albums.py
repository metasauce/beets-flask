from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from beets_flask.server.routes_next.beets._types import (
    AlbumSortField,
    BulkResult,
    Cursor,
    Direction,
    MultiAlbumDocument,
    SingleAlbumDocument,
    Sort,
)
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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


class TestGetAlbums(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/albums/`` (bulk)."""

    _albums: ClassVar[dict[str, BeetsAlbum]] = {}

    @staticmethod
    def _url(**params: object) -> str:
        """Build the URL of the bulk albums endpoint from query params."""
        query = urlencode(params, doseq=True)
        return "/api_v1/beets/albums/" + (f"?{query}" if query else "")

    @staticmethod
    def _next_url(document: MultiAlbumDocument) -> str | None:
        """Path+query of the typed ``links.next``, or ``None`` on the last page."""
        if document.links is None or document.links.next is None:
            return None
        url = urlsplit(document.links.next)
        return url.path + "?" + url.query

    @staticmethod
    def _cursor_of(document: MultiAlbumDocument) -> str:
        """The ``cursor`` query param of the typed ``links.next``."""
        assert document.links is not None and document.links.next is not None
        return parse_qs(urlsplit(document.links.next).query)["cursor"][0]

    @staticmethod
    def _names(document: MultiAlbumDocument) -> list[str]:
        return [resource.attributes.album for resource in document.data]

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib) -> dict[str, BeetsAlbum]:
        """Create the albums used by all tests in this class.

        Five albums with distinct years, two album artists and varying
        item counts, so sorting, filtering and ``include=items`` are
        deterministic:

        - Album A (2001, Tool, 2 items), Album B (2003, Tool)
        - Album C (2000, Pink Floyd, 1 item), Album D (2004, Pink Floyd, 1)
        - Album E (2002, Tool)
        """
        albums = {
            "a": beets_lib_album(album="Album A", albumartist="Tool", year=2001),
            "b": beets_lib_album(album="Album B", albumartist="Tool", year=2003),
            "c": beets_lib_album(album="Album C", albumartist="Pink Floyd", year=2000),
            "d": beets_lib_album(album="Album D", albumartist="Pink Floyd", year=2004),
            "e": beets_lib_album(album="Album E", albumartist="Tool", year=2002),
        }
        for album in albums.values():
            self.beets_lib.add(album)
        for album_id, n_items in {
            albums["a"].id: 2,
            albums["c"].id: 1,
            albums["d"].id: 1,
        }.items():
            for i in range(n_items):
                self.beets_lib.add(
                    beets_lib_item(album_id=album_id, title=f"Track {i}")
                )

        self._albums.update(albums)
        return albums

    async def _walk(
        self, client: TestClientProtocol, expected_total: int, **params: object
    ) -> AsyncGenerator[MultiAlbumDocument, None]:
        """Walk ``links.next`` until exhausted, yielding each page's document.

        Asserts on every page: valid document, stable ``meta.total`` and a
        present ``links.self``. Termination proves that ``links.next`` is
        absent on the last page and that the next links echo the page size.
        """
        url = self._url(**params)
        while url is not None:
            response = await client.get(url)
            assert response.status_code == 200
            document = MultiAlbumDocument.model_validate(await response.get_json())
            assert document.meta is not None and document.meta.total == expected_total
            assert document.links is not None and document.links.self

            yield document
            url = self._next_url(document)

    @pytest.mark.parametrize(
        "sort, expected",
        [
            ("year", ["Album C", "Album A", "Album E", "Album B", "Album D"]),
            ("-year", ["Album D", "Album B", "Album E", "Album A", "Album C"]),
            # Newest first = reverse insertion order (ids 1..5).
            ("-added", ["Album E", "Album D", "Album C", "Album B", "Album A"]),
        ],
        ids=["asc", "desc", "newest_first"],
    )
    async def test_get_albums_walk(
        self, client: TestClientProtocol, sort: str, expected: list[str]
    ):
        """Walking ``links.next`` yields every album exactly once, in sort order."""
        names = [
            name
            async for document in self._walk(
                client, expected_total=5, sort=sort, limit=2
            )
            for name in self._names(document)
        ]
        assert names == expected

    async def test_get_albums_bare_request(self, client: TestClientProtocol):
        """A bare request applies the defaults (``-added``, limit 100)."""
        response = await client.get(self._url())
        assert response.status_code == 200

        document = MultiAlbumDocument.model_validate(await response.get_json())
        assert document.meta is not None and document.meta.total == 5
        assert len(document.data) == 5  # limit 100: single page
        assert self._names(document) == [
            "Album E",
            "Album D",
            "Album C",
            "Album B",
            "Album A",
        ]
        assert document.links is not None and document.links.next is None

    async def test_get_albums_cursor_keeps_filters(self, client: TestClientProtocol):
        """Pages after the first keep the filters of the original request."""
        names = [
            name
            async for document in self._walk(
                client,
                expected_total=3,
                sort="year",
                limit=2,
                filter_query="albumartist:Tool",
            )
            for name in self._names(document)
        ]
        assert names == ["Album A", "Album E", "Album B"]

    async def test_get_albums_include_items(self, client: TestClientProtocol):
        """``include=items`` embeds the items and is carried over by ``links.next``."""
        included: list[str] = []
        names: list[str] = []
        url = self._url(sort="year", limit=2, include="items")
        while url is not None:
            response = await client.get(url)
            assert response.status_code == 200
            document = MultiAlbumDocument.model_validate(await response.get_json())
            names.extend(self._names(document))
            included.extend(
                resource.attributes.title for resource in (document.included or [])
            )
            if document.links is not None and document.links.next is not None:
                assert "include=items" in document.links.next
            url = self._next_url(document)

        assert names == ["Album C", "Album A", "Album E", "Album B", "Album D"]
        assert sorted(included) == ["Track 0", "Track 0", "Track 0", "Track 1"]

    async def test_get_albums_filter_ids(self, client: TestClientProtocol):
        """``filter_ids`` selects explicit albums, even if some ids are unknown."""
        ids = [self._albums["a"].id, self._albums["e"].id, 999999]
        response = await client.get(self._url(filter_ids=ids, sort="year"))
        assert response.status_code == 200

        document = MultiAlbumDocument.model_validate(await response.get_json())
        assert document.meta is not None and document.meta.total == 2
        assert self._names(document) == ["Album A", "Album E"]

    async def test_get_albums_no_match(self, client: TestClientProtocol):
        """Filters matching nothing return an empty first and last page."""
        response = await client.get(self._url(filter_query="albumartist:NoSuchArtist"))
        assert response.status_code == 200

        document = MultiAlbumDocument.model_validate(await response.get_json())
        assert document.meta is not None and document.meta.total == 0
        assert document.data == []
        assert document.links is not None and document.links.next is None

    @pytest.mark.parametrize(
        "params",
        [
            {"sort": "bogus"},
            {"limit": 0},
            {"limit": 1001},
            {"cursor": "zznotbase64"},
            {"filter_query": "year:notanumber"},
            {"filter_ids": ["abc", "def"]},
            {"include": "bogus"},
        ],
        ids=[
            "bad_sort",
            "limit_zero",
            "limit_too_big",
            "bad_cursor",
            "bad_filter",
            "non_int_filter_ids",
            "bad_include",
        ],
    )
    async def test_get_albums_invalid_params(
        self, client: TestClientProtocol, params: dict[str, object]
    ):
        """Malformed query parameters -> 400."""
        response = await client.get(self._url(**params))
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "extra",
        [
            pytest.param({"sort": "year"}, id="sort"),
            pytest.param({"filter_query": "albumartist:Tool"}, id="filter_query"),
            pytest.param({"filter_ids": [1, 2]}, id="filter_ids"),
        ],
    )
    async def test_get_albums_cursor_exclusive(
        self, client: TestClientProtocol, extra: dict[str, object]
    ):
        """A cursor cannot be combined with ``sort`` or the filters."""
        response = await client.get(self._url(limit=1))
        assert response.status_code == 200
        document = MultiAlbumDocument.model_validate(await response.get_json())
        cursor = self._cursor_of(document)

        response = await client.get(self._url(cursor=cursor, **extra))
        assert response.status_code == 400

    async def test_get_albums_unknown_cursor_field(self, client: TestClientProtocol):
        """A cursor token with a forged sort field -> 400."""
        # Re-encode a valid cursor with a sort field outside AlbumSortField.
        token = Cursor[Sort[AlbumSortField]](
            sort=Sort[AlbumSortField](
                field=AlbumSortField.ADDED, direction=Direction.ASC
            )
        ).to_string()
        data = json.loads(Cursor._b64decode(token))
        data["sort"]["field"] = "path"
        forged = Cursor._b64encode(json.dumps(data, separators=(",", ":")).encode())

        response = await client.get(self._url(cursor=forged))
        assert response.status_code == 400


class TestPatchAlbums(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/albums/`` (bulk)."""

    _albums: ClassVar[dict[str, BeetsAlbum]] = {}

    @staticmethod
    def _url(**params: object) -> str:
        """Build the URL of the bulk albums endpoint from query params."""
        query = urlencode(params, doseq=True)
        return "/api_v1/beets/albums/" + (f"?{query}" if query else "")

    @pytest.fixture(scope="class", autouse=True)
    def albums(self, setup_beetslib) -> dict[str, BeetsAlbum]:
        """Two Tool albums and two Pink Floyd albums with distinct years."""
        albums = {
            "tool_2001": beets_lib_album(
                album="Album A", albumartist="Tool", year=2001
            ),
            "tool_2003": beets_lib_album(
                album="Album B", albumartist="Tool", year=2003
            ),
            "pink_2000": beets_lib_album(
                album="Album C", albumartist="Pink Floyd", year=2000
            ),
            "pink_2004": beets_lib_album(
                album="Album D", albumartist="Pink Floyd", year=2004
            ),
        }
        for album in albums.values():
            self.beets_lib.add(album)
        self._albums.update(albums)
        return albums

    async def test_patch_albums_by_query(self, client: TestClientProtocol):
        """PATCH updates all albums matching ``filter_query``."""
        response = await client.patch(
            self._url(filter_query="albumartist:Tool"),
            json={"albumartist": "Tool 2", "year": 1999},
        )
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 2

        for key in ("tool_2001", "tool_2003"):
            album = self.beets_lib.get_album(self._albums[key].id)
            assert album is not None
            assert album.albumartist == "Tool 2"
            assert album.year == 1999
            assert album.album == self._albums[key].album  # unpatched attr unchanged
        for key in ("pink_2000", "pink_2004"):
            album = self.beets_lib.get_album(self._albums[key].id)
            assert album is not None and album.albumartist == "Pink Floyd"

    async def test_patch_albums_by_ids(self, client: TestClientProtocol):
        """PATCH updates only the albums named by ``filter_ids``."""
        ids = [self._albums["pink_2000"].id, self._albums["pink_2004"].id]
        response = await client.patch(self._url(filter_ids=ids), json={"year": 2020})
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 2

        for key in ("pink_2000", "pink_2004"):
            album = self.beets_lib.get_album(self._albums[key].id)
            assert album is not None and album.year == 2020
        # Untouched albums keep their titles.
        for key in ("tool_2001", "tool_2003"):
            album = self.beets_lib.get_album(self._albums[key].id)
            assert album is not None and album.album == self._albums[key].album

    async def test_patch_albums_no_match(self, client: TestClientProtocol):
        """A filter matching nothing updates nothing but still succeeds."""
        response = await client.patch(
            self._url(filter_query="albumartist:NoSuchArtist"), json={"year": 0}
        )
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 0

        album = self.beets_lib.get_album(self._albums["tool_2001"].id)
        assert album is not None and album.album == "Album A"

    async def test_patch_albums_empty_body(self, client: TestClientProtocol):
        """PATCH without any attributes -> 400."""
        ids = [self._albums["tool_2001"].id, self._albums["pink_2000"].id]
        response = await client.patch(self._url(filter_ids=ids), json={})
        assert response.status_code == 400

        data = await response.get_json()
        assert data["type"] == "InvalidUsageError"
