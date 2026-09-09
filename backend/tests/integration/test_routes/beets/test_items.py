from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from beets_flask.server.routes_next.beets._types import (
    BulkResult,
    Cursor,
    Direction,
    ItemSortField,
    MultiItemDocument,
    SingleItemDocument,
    Sort,
)
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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


class TestGetItems(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/items/`` (bulk)."""

    _items: ClassVar[dict[str, BeetsItem]] = {}

    @staticmethod
    def _url(**params: object) -> str:
        """Build the URL of the bulk items endpoint from query params."""
        query = urlencode(params, doseq=True)
        return "/api_v1/beets/items/" + (f"?{query}" if query else "")

    @staticmethod
    def _titles(document: MultiItemDocument) -> list[str | None]:
        return [resource.attributes.title for resource in document.data]

    @staticmethod
    def _next_url(document: MultiItemDocument) -> str | None:
        """Path+query of the typed ``links.next``, or ``None`` on the last page."""
        if document.links is None or document.links.next is None:
            return None
        url = urlsplit(document.links.next)
        return url.path + "?" + url.query

    @staticmethod
    def _cursor_of(document: MultiItemDocument) -> str:
        """The ``cursor`` query param of the typed ``links.next``."""
        assert document.links is not None and document.links.next is not None
        return parse_qs(urlsplit(document.links.next).query)["cursor"][0]

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib) -> dict[str, BeetsItem]:
        """Create the items used by all tests in this class.

        Five items with distinct years and two artists, so sorting and
        filtering are deterministic (``year`` is not exposed in the item
        attributes, but the titles encode the sort order):

        - Tool A (2001), Tool B (2003), Tool C (2002)
        - Pink 0 (2000), Pink 4 (2004)
        """
        tool_a = beets_lib_item(title="Tool A", year=2001, artist="Tool")
        pink_0 = beets_lib_item(title="Pink 0", year=2000, artist="Pink Floyd")
        tool_b = beets_lib_item(title="Tool B", year=2003, artist="Tool")
        pink_4 = beets_lib_item(title="Pink 4", year=2004, artist="Pink Floyd")
        tool_c = beets_lib_item(title="Tool C", year=2002, artist="Tool")
        for item in (tool_a, pink_0, tool_b, pink_4, tool_c):
            self.beets_lib.add(item)

        self._items.update(
            tool_a=tool_a,
            pink_2000=pink_0,
            tool_b=tool_b,
            pink_2004=pink_4,
            tool_c=tool_c,
        )
        return self._items

    async def _walk(
        self, client: TestClientProtocol, expected_total: int, **params: object
    ) -> AsyncGenerator[MultiItemDocument, None]:
        """Walk ``links.next`` until exhausted, yielding each page's document.

        Asserts on every page: valid document, stable ``meta.total`` and a
        present ``links.self``. Termination proves that ``links.next`` is
        absent on the last page and that the next links echo the page size
        (otherwise the walk would never terminate or would skip rows).
        """
        url = self._url(**params)
        while url is not None:
            response = await client.get(url)
            assert response.status_code == 200
            document = MultiItemDocument.model_validate(await response.get_json())
            assert document.meta is not None and document.meta.total == expected_total
            assert document.links is not None and document.links.self

            yield document
            url = self._next_url(document)

    @pytest.mark.parametrize(
        "sort, expected",
        [
            ("year", ["Pink 0", "Tool A", "Tool C", "Tool B", "Pink 4"]),
            ("-year", ["Pink 4", "Tool B", "Tool C", "Tool A", "Pink 0"]),
            # Absent sort falls back to ``-added`` (newest first = reverse ids).
            ("-added", ["Tool C", "Pink 4", "Tool B", "Pink 0", "Tool A"]),
        ],
        ids=["asc", "desc", "newest_first"],
    )
    async def test_get_items_walk(
        self, client: TestClientProtocol, sort: str, expected: list[str]
    ):
        """Walking ``links.next`` yields every item exactly once, in sort order."""
        titles = [
            title
            async for document in self._walk(
                client, expected_total=5, sort=sort, limit=2
            )
            for title in self._titles(document)
        ]
        assert titles == expected

    async def test_get_items_cursor_keeps_filters(self, client: TestClientProtocol):
        """Pages after the first keep the filters of the original request."""
        titles = [
            title
            async for document in self._walk(
                client,
                expected_total=3,
                sort="year",
                limit=2,
                filter_query="artist:Tool",
            )
            for title in self._titles(document)
        ]
        assert titles == ["Tool A", "Tool C", "Tool B"]

    async def test_get_items_bare_request(self, client: TestClientProtocol):
        """A bare request applies the defaults (``-added``, limit 100)."""
        response = await client.get(self._url())
        assert response.status_code == 200

        document = MultiItemDocument.model_validate(await response.get_json())
        assert document.meta is not None and document.meta.total == 5
        assert len(document.data) == 5  # limit 100: single page
        assert self._titles(document) == [
            "Tool C",
            "Pink 4",
            "Tool B",
            "Pink 0",
            "Tool A",
        ]
        assert document.links is not None and document.links.next is None

    async def test_get_items_filter_ids(self, client: TestClientProtocol):
        """``filter_ids`` selects explicit items, even if some ids are unknown."""
        known = self._items["tool_a"].id
        response = await client.get(self._url(filter_ids=[known, 999999], sort="year"))
        assert response.status_code == 200

        document = MultiItemDocument.model_validate(await response.get_json())
        assert document.meta is not None and document.meta.total == 1
        assert self._titles(document) == ["Tool A"]

    async def test_get_items_no_match(self, client: TestClientProtocol):
        """Filters matching nothing return an empty first and last page."""
        response = await client.get(self._url(filter_query="artist:NoSuchArtist"))
        assert response.status_code == 200

        document = MultiItemDocument.model_validate(await response.get_json())
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
        ],
        ids=[
            "bad_sort",
            "limit_zero",
            "limit_too_big",
            "bad_cursor",
            "bad_filter",
            "non_int_filter_ids",
        ],
    )
    async def test_get_items_invalid_params(
        self, client: TestClientProtocol, params: dict[str, object]
    ):
        """Malformed query parameters -> 400."""
        response = await client.get(self._url(**params))
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "extra",
        [
            pytest.param({"sort": "year"}, id="sort"),
            pytest.param({"filter_query": "artist:Tool"}, id="filter_query"),
            pytest.param({"filter_ids": [1, 2]}, id="filter_ids"),
        ],
    )
    async def test_get_items_cursor_exclusive(
        self, client: TestClientProtocol, extra: dict[str, object]
    ):
        """A cursor cannot be combined with ``sort`` or the filters."""
        response = await client.get(self._url(limit=1))
        assert response.status_code == 200
        document = MultiItemDocument.model_validate(await response.get_json())
        cursor = self._cursor_of(document)

        response = await client.get(self._url(cursor=cursor, **extra))
        assert response.status_code == 400

    async def test_get_items_unknown_cursor_field(self, client: TestClientProtocol):
        """A cursor token with a forged sort field -> 400."""
        # Re-encode a valid cursor with a sort field outside ItemSortField.
        token = Cursor[Sort[ItemSortField]](
            sort=Sort[ItemSortField](field=ItemSortField.ADDED, direction=Direction.ASC)
        ).to_string()
        data = json.loads(Cursor._b64decode(token))
        data["sort"]["field"] = "path"
        forged = Cursor._b64encode(json.dumps(data, separators=(",", ":")).encode())

        response = await client.get(self._url(cursor=forged))
        assert response.status_code == 400


class TestPatchItems(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/items/`` (bulk)."""

    _items: ClassVar[dict[str, BeetsItem]] = {}

    @staticmethod
    def _url(**params: object) -> str:
        """Build the URL of the bulk items endpoint from query params."""
        query = urlencode(params, doseq=True)
        return "/api_v1/beets/items/" + (f"?{query}" if query else "")

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib) -> dict[str, BeetsItem]:
        """Three Tool items and two Radiohead items with distinct titles."""
        items = {
            "tool_a": beets_lib_item(title="Tool A", artist="Tool"),
            "tool_b": beets_lib_item(title="Tool B", artist="Tool"),
            "tool_c": beets_lib_item(title="Tool C", artist="Tool"),
            "radio_d": beets_lib_item(title="Radio D", artist="Radiohead"),
            "radio_e": beets_lib_item(title="Radio E", artist="Radiohead"),
        }
        for item in items.values():
            self.beets_lib.add(item)
        self._items.update(items)
        return items

    async def test_patch_items_by_query(self, client: TestClientProtocol):
        """PATCH updates all items matching ``filter_query``."""
        response = await client.patch(
            self._url(filter_query="artist:Tool"), json={"artist": "Tool 2"}
        )
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 3

        # Persisted; the non-matching items are untouched.
        for key in ("tool_a", "tool_b", "tool_c"):
            item = self.beets_lib.get_item(self._items[key].id)
            assert item is not None and item.artist == "Tool 2"
            assert item.title == self._items[key].title  # unpatched attr unchanged
        for key in ("radio_d", "radio_e"):
            item = self.beets_lib.get_item(self._items[key].id)
            assert item is not None and item.artist == "Radiohead"

    async def test_patch_items_by_ids(self, client: TestClientProtocol):
        """PATCH updates only the items named by ``filter_ids``."""
        ids = [self._items["tool_a"].id, self._items["radio_d"].id]
        response = await client.patch(
            self._url(filter_ids=ids), json={"title": "Renamed"}
        )
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 2

        for key in ("tool_a", "radio_d"):
            item = self.beets_lib.get_item(self._items[key].id)
            assert item is not None and item.title == "Renamed"
        # Untouched items keep their titles.
        for key in ("tool_b", "radio_e"):
            item = self.beets_lib.get_item(self._items[key].id)
            assert item is not None and item.title == self._items[key].title

    async def test_patch_items_no_match(self, client: TestClientProtocol):
        """A filter matching nothing updates nothing but still succeeds."""
        response = await client.patch(
            self._url(filter_query="artist:NoSuchArtist"), json={"title": "X"}
        )
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 0

        item = self.beets_lib.get_item(self._items["radio_e"].id)
        assert item is not None and item.title == "Radio E"

    async def test_patch_items_empty_body(self, client: TestClientProtocol):
        """PATCH without any attributes -> 400."""
        ids = [self._items["tool_b"].id, self._items["radio_e"].id]
        response = await client.patch(self._url(filter_ids=ids), json={})
        assert response.status_code == 400

        data = await response.get_json()
        assert data["type"] == "InvalidUsageError"


class TestDeleteItems(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/items/`` (bulk)."""

    _items: ClassVar[dict[str, BeetsItem]] = {}

    @staticmethod
    def _url(**params: object) -> str:
        """Build the URL of the bulk items endpoint from query params."""
        query = urlencode(params, doseq=True)
        return "/api_v1/beets/items/" + (f"?{query}" if query else "")

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib) -> dict[str, BeetsItem]:
        """Each test deletes its own group; the survivor never matches."""
        items = {
            "tool_a": beets_lib_item(title="Tool A", artist="Tool"),
            "tool_b": beets_lib_item(title="Tool B", artist="Tool"),
            "tool_c": beets_lib_item(title="Tool C", artist="Tool"),
            "radio_d": beets_lib_item(title="Radio D", artist="Radiohead"),
            "radio_e": beets_lib_item(title="Radio E", artist="Radiohead"),
            "survivor": beets_lib_item(title="Solo S", artist="Solo Artist"),
        }
        for item in items.values():
            self.beets_lib.add(item)
        self._items.update(items)
        return items

    async def _assert_deleted(self, keys: list[str]):
        for key in keys:
            assert self.beets_lib.get_item(self._items[key].id) is None
        assert self.beets_lib.get_item(self._items["survivor"].id) is not None

    async def test_delete_items_by_query(self, client: TestClientProtocol):
        """DELETE removes all items matching ``filter_query``."""
        response = await client.delete(self._url(filter_query="artist:Tool"))
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 3
        await self._assert_deleted(["tool_a", "tool_b", "tool_c"])

    async def test_delete_items_by_ids(self, client: TestClientProtocol):
        """DELETE removes only the items named by ``filter_ids``."""
        ids = [self._items["radio_d"].id, self._items["radio_e"].id, 999999]
        response = await client.delete(self._url(filter_ids=ids))
        assert response.status_code == 200
        assert BulkResult.model_validate(await response.get_json()).meta.total == 2
        await self._assert_deleted(["radio_d", "radio_e"])
