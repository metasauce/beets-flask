"""Tests for the new beets items API endpoints.

Covers the implemented endpoints of ``beets_flask/server/routes/beets/items.py``:

- ``GET /api_v1/beets/items/<item_id>``
- ``PATCH /api_v1/beets/items/<item_id>``
- ``DELETE /api_v1/beets/items/<item_id>``
- ``GET /api_v1/beets/items/`` (bulk)
- ``PATCH /api_v1/beets/items/`` (bulk)
- ``DELETE /api_v1/beets/items/`` (bulk)
"""

import json
import os
from pathlib import Path

import pytest
from beets.library import Item
from quart.typing import TestClientProtocol as Client

from beets_flask.config import get_config
from beets_flask.server.routes.beets._cursor import Cursor, PaginatedQuery
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

    async def test_patch_item_null_clears_field(self, client: Client):
        """PATCH with an explicit ``null`` clears the title."""
        item = self.beets_lib.get_item(self._items["a"].id)
        assert item is not None
        new_title = "Cleared Title"
        self.beets_lib.get_item(item.id).update({"title": new_title})
        self.beets_lib.get_item(item.id).store()

        response = await client.patch(_item_url(item.id), json={"title": None})
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"]["attributes"]["title"] == ""

        stored = self.beets_lib.get_item(item.id)
        assert stored is not None
        assert stored.title == "", "Title was not cleared"

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


# ---------------------------------- Bulk Get -------------------------------- #


class TestGetItems(IsolatedBeetsLibraryMixin):
    """Tests for ``GET /api_v1/beets/items/`` (bulk)."""

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create 25 items with distinct titles and five artists."""
        for i in range(25):
            self.beets_lib.add(
                beets_lib_item(title=f"Bulk Item {i:02d}", artist=f"Artist{i % 5}")
            )

    async def test_get_items_pagination(self, client: Client):
        """Iterate all pages via the ``links.next`` cursor."""
        next_url = "/api_v1/beets/items/?limit=10"
        titles = []
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 25
            assert "self" in data["links"]
            titles.extend(i["attributes"]["title"] for i in data["data"])
            pages += 1
            next_url = data["links"].get("next")

        assert pages == 3, "Expected three pages of ten items"
        assert len(titles) == 25, "Not all items were returned"
        assert len(set(titles)) == 25, "Items were returned more than once"

    async def test_get_items_default_limit(self, client: Client):
        """Without ``limit``, the default page size applies."""
        response = await client.get("/api_v1/beets/items/")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert len(data["data"]) == 25
        assert "next" not in data.get("links", {}), "Unexpected next page"

    async def test_get_items_sort(self, client: Client):
        """Sort by title ascending and descending."""
        response = await client.get("/api_v1/beets/items/?sort=title&limit=100")
        data = await response.get_json()
        titles = [i["attributes"]["title"] for i in data["data"]]
        assert titles == sorted(titles), "Items are not sorted ascending"

        response = await client.get("/api_v1/beets/items/?sort=-title&limit=100")
        data = await response.get_json()
        titles = [i["attributes"]["title"] for i in data["data"]]
        assert titles == sorted(titles, reverse=True), "Items are not sorted descending"

    async def test_get_items_descending_pagination(self, client: Client):
        """Iterate all pages sorted descending via the cursor."""
        next_url = "/api_v1/beets/items/?sort=-title&limit=5"
        titles = []
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 25
            titles.extend(i["attributes"]["title"] for i in data["data"])
            pages += 1
            next_url = data["links"].get("next")

        assert pages == 5, "Expected five pages of five items"
        assert titles == sorted(titles, reverse=True), "Items are not sorted descending"
        assert len(titles) == 25, "Not all items were returned"

    async def test_get_items_filter_query(self, client: Client):
        """Filter by a beets query string."""
        response = await client.get("/api_v1/beets/items/?filter_query=artist:Artist2")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        expected = {f"Bulk Item {i:02d}" for i in range(25) if i % 5 == 2}
        titles = {i["attributes"]["title"] for i in data["data"]}
        assert titles == expected, "Filtered items do not match the query"
        assert data["meta"]["total"] == 5

    async def test_get_items_invalid_filter_query(self, client: Client):
        """A filter value that does not match its field type -> 400."""
        response = await client.get("/api_v1/beets/items/?filter_query=year:notanumber")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_cursor_with_invalid_filter(self, client: Client):
        """A cursor token carrying an unparseable filter query -> 400."""
        token = json.dumps({"s": "-added", "q": "year:notanumber"}).encode().hex()
        response = await client.get(f"/api_v1/beets/items/?cursor={token}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_filter_ids(self, client: Client):
        """Filter by explicit ids."""
        ids = [str(i.id) for i in list(self.beets_lib.items())[:2]]
        response = await client.get(
            "/api_v1/beets/items/?filter_ids=" + "&filter_ids=".join(ids)
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert {i["id"] for i in data["data"]} == set(ids)
        assert data["meta"]["total"] == 2

    async def test_get_items_filter_ids_single(self, client: Client):
        """A single ``filter_ids`` value is accepted."""
        item = list(self.beets_lib.items())[0]

        response = await client.get(f"/api_v1/beets/items/?filter_ids={item.id}")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert data["data"][0]["id"] == str(item.id)

    async def test_get_items_invalid_filter_ids(self, client: Client):
        """A non-numeric ``filter_ids`` value -> 400."""
        response = await client.get("/api_v1/beets/items/?filter_ids=abc")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_items_cursor_with_invalid_filter_ids(self, client: Client):
        """A cursor token carrying non-numeric filter ids -> 400."""
        token = json.dumps({"s": "-added", "f": ["abc"]}).encode().hex()
        response = await client.get(f"/api_v1/beets/items/?cursor={token}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_empty(self, client: Client):
        """A filter without matches returns an empty page."""
        response = await client.get(
            "/api_v1/beets/items/?filter_query=title:Nonexistent"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["data"] == []
        assert data["meta"]["total"] == 0
        assert "next" not in data.get("links", {})

    async def test_get_items_invalid_cursor(self, client: Client):
        """An invalid cursor token -> 400."""
        response = await client.get("/api_v1/beets/items/?cursor=bogus")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_invalid_sort_field(self, client: Client):
        """Sorting by a disallowed field -> 400."""
        response = await client.get("/api_v1/beets/items/?sort=+bogus")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_items_limit_too_high(self, client: Client):
        """A limit above the maximum -> 400."""
        response = await client.get("/api_v1/beets/items/?limit=100000")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    @pytest.mark.parametrize("limit", ["0", "-1"], ids=["zero", "negative"])
    async def test_get_items_limit_too_low(self, client: Client, limit: str):
        """A non-positive limit -> 400."""
        response = await client.get(f"/api_v1/beets/items/?limit={limit}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_empty_sort(self, client: Client):
        """An empty ``sort`` value -> 400."""
        response = await client.get("/api_v1/beets/items/?sort=&limit=100")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_items_sort_without_field(self, client: Client):
        """A ``sort`` without a field -> 400."""
        response = await client.get("/api_v1/beets/items/?sort=,&limit=100")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_items_sort_sign_without_field(self, client: Client):
        """A sort sign without a field -> 400."""
        response = await client.get("/api_v1/beets/items/?sort=%2B")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "QuerystringValidationError"

    async def test_get_items_cursor_with_crafted_sort(self, client: Client):
        """A cursor token with a crafted sort field -> 400."""
        token = json.dumps({"s": "+bogus", "v": "x", "i": 1}).encode().hex()
        response = await client.get(f"/api_v1/beets/items/?cursor={token}")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_numeric_cursor_value(self, client: Client):
        """A cursor with a numeric sort value is coerced to a string."""
        token = json.dumps({"s": "+title", "v": 123, "i": 1}).encode().hex()
        response = await client.get(f"/api_v1/beets/items/?cursor={token}&limit=100")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert len(data["data"]) == 25

    async def test_get_items_cursor_with_sort_rejected(self, client: Client):
        """``cursor`` combined with ``sort`` -> 400."""
        token = Cursor.initial("+title").to_string()
        response = await client.get(f"/api_v1/beets/items/?cursor={token}&sort=title")
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"

    async def test_get_items_cursor_with_filter_rejected(self, client: Client):
        """``cursor`` combined with filters -> 400."""
        token = Cursor.initial("+title").to_string()
        for params in ("filter_query=artist:Artist2", "filter_ids=1&filter_ids=2"):
            response = await client.get(f"/api_v1/beets/items/?cursor={token}&{params}")
            data = await response.get_json()
            assert response.status_code == 400, f"{params} should be rejected"
            assert data["type"] == "InvalidUsageException"

    async def test_get_items_filtered_pagination(self, client: Client):
        """Filters survive pagination via the self-contained cursor."""
        next_url = "/api_v1/beets/items/?filter_query=artist:Artist2&limit=2"
        titles = []
        pages = 0
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 5
            titles.extend(i["attributes"]["title"] for i in data["data"])
            pages += 1
            next_url = data["links"].get("next")
            if next_url:
                # The cursor is self-contained: no filter params in the link
                for param in ("filter_query", "filter_ids", "sort"):
                    assert f"{param}=" not in next_url, f"{param} in next link"

        expected = {f"Bulk Item {i:02d}" for i in range(25) if i % 5 == 2}
        assert pages == 3, "Expected three pages of two items"
        assert set(titles) == expected, "Filtered items do not match the query"
        assert len(titles) == 5, "Items were returned more than once"

    async def test_get_items_filtered_pagination_by_ids(self, client: Client):
        """Id filters survive pagination via the self-contained cursor."""
        ids = [str(i.id) for i in list(self.beets_lib.items())[:3]]
        next_url = "/api_v1/beets/items/?limit=2&filter_ids=" + "&filter_ids=".join(ids)
        found = []
        while next_url:
            response = await client.get(next_url)
            data = await response.get_json()
            assert response.status_code == 200, "Response status code is not 200"
            assert data["meta"]["total"] == 3
            found.extend(i["id"] for i in data["data"])
            next_url = data["links"].get("next")

        assert set(found) == set(ids), "Id filtered pagination lost items"
        assert len(found) == 3

    async def test_get_items_next_link_strips_sort(self, client: Client):
        """The ``links.next`` of a sorted page carries no ``sort`` and stays sorted."""
        response = await client.get("/api_v1/beets/items/?sort=title&limit=5")
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        first_titles = [i["attributes"]["title"] for i in data["data"]]
        assert first_titles == sorted(first_titles)

        next_url = data["links"]["next"]
        assert "sort=" not in next_url, "Next link must not carry the sort parameter"

        response = await client.get(next_url)
        data = await response.get_json()
        assert response.status_code == 200, "Response status code is not 200"
        second_titles = [i["attributes"]["title"] for i in data["data"]]
        assert second_titles == sorted(second_titles)
        # The second page continues the same order after the first page
        assert all(t1 < t2 for t1 in first_titles for t2 in second_titles)


# -------------------------------- Bulk Delete ------------------------------- #


class TestDeleteItems(IsolatedBeetsLibraryMixin):
    """Tests for ``DELETE /api_v1/beets/items/`` (bulk)."""

    _audio_src = (
        Path(__file__).parent.parent.parent.parent / "data" / "audio" / "test.mp3"
    )

    def _add_item(self, title: str, artist: str, file_name: str | None = None) -> Item:
        """Add an item to the library, optionally with a dedicated audio file.

        Each test creates the items it needs, so the tests are independent
        of each other and of their execution order.
        """
        import shutil

        item = beets_lib_item(title=title, artist=artist)
        self.beets_lib.add(item)
        if file_name is not None:
            path = _item_file(file_name)
            shutil.copy(self._audio_src, path)
            item.path = str(path).encode()
            item.store()
        return item

    def _ids_of(self, artist: str) -> set[int]:
        """The ids of all items by the given artist."""
        return {i.id for i in self.beets_lib.items(f"artist:{artist}")}

    async def test_delete_items_filter_query(self, client: Client):
        """DELETE removes only the items matching the filter."""
        group_a = [self._add_item(f"Bulk Delete {i}", "GroupA") for i in range(3)]
        group_b = [self._add_item(f"Bulk Delete {i}", "GroupB") for i in range(3)]

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=artist:GroupA"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 3
        assert self._ids_of("GroupA") == set(), "GroupA items were not deleted"
        assert self._ids_of("GroupB") == {i.id for i in group_b}, (
            "Items of the other group were deleted"
        )
        assert all(self.beets_lib.get_item(i.id) is None for i in group_a)

    async def test_delete_items_invalid_filter_query(self, client: Client):
        """DELETE with an unparseable filter query -> 400, nothing deleted."""
        item = self._add_item("Kept Item", "InvalidQueryGroup")

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=year:notanumber"
        )
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self.beets_lib.get_item(item.id) is not None, "Item was deleted"

    async def test_delete_items_filter_ids(self, client: Client):
        """DELETE removes only the items with the given ids."""
        items = [self._add_item(f"Id Item {i}", "IdArtist") for i in range(3)]
        ids = [items[0].id, items[1].id]

        response = await client.delete(
            "/api_v1/beets/items/?filter_ids=" + "&filter_ids=".join(map(str, ids))
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert all(self.beets_lib.get_item(i) is None for i in ids), (
            "Items with the given ids remain"
        )
        assert self.beets_lib.get_item(items[2].id) is not None, (
            "Item without a matching id was deleted"
        )

    async def test_delete_items_no_filter(self, client: Client):
        """DELETE without a filter removes all items."""
        for i in range(3):
            self._add_item(f"All Item {i}", "AllArtist")
        expected = len(list(self.beets_lib.items()))

        response = await client.delete("/api_v1/beets/items/")
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == expected
        assert list(self.beets_lib.items()) == [], "Library is not empty"

    async def test_delete_items_no_match(self, client: Client):
        """A filter without matches deletes nothing and reports zero."""
        item = self._add_item("Kept Item", "KeptArtist")

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=title:Nonexistent"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 0
        assert self.beets_lib.get_item(item.id) is not None, "Item was deleted"

    async def test_delete_items_readonly(self, client: Client):
        """DELETE must fail and not modify the library when it is read-only."""
        item = self._add_item("Readonly Item", "ReadonlyArtist")

        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.delete(
                "/api_v1/beets/items/?filter_query=artist:ReadonlyArtist"
            )
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self.beets_lib.get_item(item.id) is not None, (
            "Item was removed even though the library is read-only"
        )

    async def test_delete_items_keeps_files_by_default(self, client: Client):
        """DELETE without ``delete_file`` keeps the files on disk."""
        items = [
            self._add_item(f"Keep File {i}", "KeepArtist", f"bulk_delete_keep_{i}.mp3")
            for i in range(2)
        ]
        paths = [_item_file(f"bulk_delete_keep_{i}.mp3") for i in range(2)]
        assert all(p.exists() for p in paths)

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=artist:KeepArtist"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert all(p.exists() for p in paths), "Files were deleted without delete_file"
        assert all(self.beets_lib.get_item(i.id) is None for i in items)

    async def test_delete_items_with_delete_file(self, client: Client):
        """DELETE with ``delete_file=true`` also removes the files from disk."""
        items = [
            self._add_item(
                f"Remove File {i}", "RemoveArtist", f"bulk_delete_rm_{i}.mp3"
            )
            for i in range(2)
        ]
        paths = [_item_file(f"bulk_delete_rm_{i}.mp3") for i in range(2)]
        assert all(p.exists() for p in paths)

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=artist:RemoveArtist&delete_file=true"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert all(not p.exists() for p in paths), "Files were not deleted"
        assert all(self.beets_lib.get_item(i.id) is None for i in items)

    async def test_delete_items_delete_file_false(self, client: Client):
        """DELETE with an explicit ``delete_file=false`` keeps the files."""
        item = self._add_item("False Item", "FalseArtist", "bulk_delete_false.mp3")
        path = _item_file("bulk_delete_false.mp3")
        assert path.exists()

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=artist:FalseArtist&delete_file=false"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert path.exists(), "File was deleted although delete_file=false"
        assert self.beets_lib.get_item(item.id) is None

    async def test_delete_items_last_item_removes_album(self, client: Client):
        """Deleting the last items of an album removes the album as well."""
        a = beets_lib_item(
            title="Album Item A", artist="AlbumArtist", album="The Album"
        )
        b = beets_lib_item(
            title="Album Item B", artist="AlbumArtist", album="The Album"
        )
        album = self.beets_lib.add_album([a, b])
        assert album.id is not None

        response = await client.delete(
            "/api_v1/beets/items/?filter_query=artist:AlbumArtist"
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self.beets_lib.get_album(album.id) is None, "Album was not removed"
        assert self.beets_lib.get_item(a.id) is None
        assert self.beets_lib.get_item(b.id) is None


class TestPaginatedQuery:
    """Direct unit tests for the PaginatedQuery helper."""

    def test_match(self):
        """The SQL clause filters, so match() accepts everything."""
        query = PaginatedQuery(Cursor.initial("+title"), 10, "items")
        assert query.match(None)


class TestCursorNormalizeSort:
    """Direct unit tests for the cursor sort edge cases."""

    def test_empty_sort(self):
        """An empty sort falls back to the default."""
        assert Cursor.normalize_sort("") == "-added"
        assert Cursor.normalize_sort(" ") == "-added"

    def test_sort_without_field(self):
        """A sort without a field falls back to the default."""
        assert Cursor.normalize_sort(",") == "-added"
        assert Cursor.normalize_sort(" , -title") == "-added"

    def test_sign_without_field(self):
        """A sort sign without a field is rejected."""
        with pytest.raises(ValueError):
            Cursor.normalize_sort("+")


class TestGetItemsSqlLimit(IsolatedBeetsLibraryMixin):
    """Regression test: pagination must not load all matching items."""

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create 100 items to prove the page query is limited."""
        for i in range(100):
            self.beets_lib.add(beets_lib_item(title=f"Sql Item {i:03d}"))

    async def test_get_items_sql_is_limited(self, client: Client):
        """The page query carries a ``LIMIT``, so only a page is fetched."""
        from beets.dbcore.db import Transaction

        statements = []
        original_query = Transaction.query

        def spy(self, statement, subvals=()):
            statements.append(str(statement))
            return original_query(self, statement, subvals)

        Transaction.query = spy
        try:
            response = await client.get("/api_v1/beets/items/?limit=10")
            data = await response.get_json()
        finally:
            Transaction.query = original_query

        assert response.status_code == 200, "Response status code is not 200"
        assert len(data["data"]) == 10
        assert data["meta"]["total"] == 100

        page_selects = [s for s in statements if "ORDER BY" in s]
        assert page_selects, "No page query was executed"
        assert "LIMIT 11" in page_selects[0], (
            f"No LIMIT in SQL: {page_selects[0][:200]}"
        )


class TestPatchItems(IsolatedBeetsLibraryMixin):
    """Tests for ``PATCH /api_v1/beets/items/`` (bulk)."""

    _items: dict[str, Item] = {}

    @pytest.fixture(scope="class", autouse=True)
    def items(self, setup_beetslib):  # type: ignore
        """Create items with dedicated audio files, grouped by artist."""
        import shutil

        audio_src = (
            Path(__file__).parent.parent.parent.parent / "data" / "audio" / "test.mp3"
        )
        for i in range(6):
            group = "GroupA" if i < 3 else "GroupB"
            item = beets_lib_item(title=f"Bulk Patch {i}", artist=group)
            self.beets_lib.add(item)
            path = _item_file(f"bulk_patch_{i}.mp3")
            shutil.copy(audio_src, path)
            item.path = str(path).encode()
            item.store()
            self._items[i] = item

    def _titles_of(self, artist: str) -> set[str]:
        """The titles of all items by the given artist."""
        return {i.title for i in self.beets_lib.items(f"artist:{artist}")}

    async def test_patch_items_readonly(self, client: Client):
        """PATCH must fail when the library is read-only."""
        config = get_config()
        config.data.gui.library.readonly = True
        try:
            response = await client.patch(
                "/api_v1/beets/items/?filter_query=artist:GroupA",
                json={"title": "Should Not Apply"},
            )
        finally:
            config.data.gui.library.readonly = False
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self._titles_of("GroupA") == {
            "Bulk Patch 0",
            "Bulk Patch 1",
            "Bulk Patch 2",
        }

    async def test_patch_items_filter_query(self, client: Client):
        """PATCH applies the body to all items matching the filter."""
        response = await client.patch(
            "/api_v1/beets/items/?filter_query=artist:GroupA",
            json={"title": "Renamed"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 3
        assert self._titles_of("GroupA") == {"Renamed"}
        # items of the other group are untouched
        assert self._titles_of("GroupB") == {
            "Bulk Patch 3",
            "Bulk Patch 4",
            "Bulk Patch 5",
        }

    async def test_patch_items_invalid_filter_query(self, client: Client):
        """PATCH with an unparseable filter query -> 400, nothing updated."""
        item = beets_lib_item(title="Kept Item", artist="InvalidQueryGroup")
        self.beets_lib.add(item)

        response = await client.patch(
            "/api_v1/beets/items/?filter_query=year:notanumber",
            json={"title": "Should Not Apply"},
        )
        data = await response.get_json()

        assert response.status_code == 400, "Response status code is not 400"
        assert data["type"] == "InvalidUsageException"
        assert self.beets_lib.get_item(item.id).title == "Kept Item"

    async def test_patch_items_filter_ids(self, client: Client):
        """PATCH applies the body to the items with the given ids."""
        response = await client.patch(
            "/api_v1/beets/items/?filter_ids=3&filter_ids=4",
            json={"title": "Id Renamed"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 2
        assert self.beets_lib.get_item(3).title == "Id Renamed"
        assert self.beets_lib.get_item(4).title == "Id Renamed"

    async def test_patch_items_null_clears_field(self, client: Client):
        """PATCH with an explicit ``null`` clears the field."""
        response = await client.patch(
            "/api_v1/beets/items/?filter_query=artist:GroupB",
            json={"title": None},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 3
        assert self._titles_of("GroupB") == {""}

    async def test_patch_items_empty_body(self, client: Client):
        """PATCH with an empty body is a no-op, but reports the matched count."""
        before = self._titles_of("GroupA")

        response = await client.patch(
            "/api_v1/beets/items/?filter_query=artist:GroupA", json={}
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 3
        assert self._titles_of("GroupA") == before, "Empty body changed items"

    async def test_patch_items_writes_file_tags(self, client: Client):
        """PATCH writes the new title into the files' tags, like the single patch."""
        import shutil

        from mediafile import MediaFile

        item = beets_lib_item(title="File Tag Item", artist="FileTagArtist")
        self.beets_lib.add(item)
        path = _item_file("bulk_patch_filetag.mp3")
        shutil.copy(
            Path(__file__).parent.parent.parent.parent / "data" / "audio" / "test.mp3",
            path,
        )
        item.path = str(path).encode()
        item.store()

        response = await client.patch(
            "/api_v1/beets/items/?filter_query=artist:FileTagArtist",
            json={"title": "File Renamed"},
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == 1
        assert MediaFile(str(path)).title == "File Renamed", "File tag not updated"

    async def test_patch_items_no_filter(self, client: Client):
        """PATCH without a filter applies the body to all items."""
        total = len(list(self.beets_lib.items()))

        response = await client.patch(
            "/api_v1/beets/items/", json={"title": "All Renamed"}
        )
        data = await response.get_json()

        assert response.status_code == 200, "Response status code is not 200"
        assert data["meta"]["total"] == total
        assert {i.title for i in self.beets_lib.items()} == {"All Renamed"}
