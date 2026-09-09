from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from beets_flask.server.routes_next.beets._types import SingleAlbumDocument
from tests.conftest import beets_lib_album, beets_lib_item
from tests.mixins.database import IsolatedBeetsLibraryMixin

if TYPE_CHECKING:
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
