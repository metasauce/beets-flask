"""Tidal provider: authentication and album art resolution."""

from __future__ import annotations

import asyncio
import re
from functools import cache
from typing import TYPE_CHECKING, ClassVar, Literal, NotRequired, TypedDict, cast

import aiohttp
from beets import plugins as beets_plugins
from beets.exceptions import UserError

from beets_flask.logger import log

from .. import ArtResult, ArtSource, AuthExtension, PkceData

if TYPE_CHECKING:
    from beetsplug.tidal import TidalPlugin
    from beetsplug.tidal.api_types import AlbumDocument


class TidalAuth(AuthExtension):
    """Authenticate with Tidal.

    Implements the same auth flow as in beets' Tidal plugin, using the
    `requests-oauthlib` session to generate the auth URL and exchange the code for a
    token.
    """

    name: ClassVar[str] = "tidal"

    @classmethod
    def is_enabled(cls) -> bool:
        return cls.tidal_plugin() is not None

    @classmethod
    @cache
    def tidal_plugin(cls) -> TidalPlugin | None:
        """Return beets' loaded Tidal plugin, if enabled."""
        try:
            from beetsplug.tidal import TidalPlugin as _TidalPlugin
        except ImportError as err:
            log.debug("Tidal plugin is unavailable: %s", err)
            return None

        return next(
            (
                plugin
                for plugin in beets_plugins.find_plugins()
                if isinstance(plugin, _TidalPlugin)
            ),
            None,
        )

    def is_authenticated(self) -> bool:
        """Check if the user is authenticated with Tidal."""
        plugin = self.tidal_plugin()
        if plugin is None:
            return False

        # Raises UserError if not authenticated
        try:
            plugin.require_authentication()
        except UserError:
            return False

        return True

    def start_authentication(self) -> tuple[PkceData, str]:
        """Start the PKCE flow: build the login URL and return the flow state.

        The PKCE verifier and CSRF state live on the OAuth session object,
        which is process-local, so they are returned here as sensitive
        :class:`PkceData`. The caller is responsible for persisting them
        server-side until the flow is completed.
        """
        plugin = self.tidal_plugin()
        if plugin is None:
            raise RuntimeError("The Tidal plugin is not enabled.")

        session = plugin.api.session
        auth_url, state = session.authorization_url("https://login.tidal.com/authorize")
        pkce = PkceData(code_verifier=session._code_verifier, state=state)
        return pkce, auth_url

    def complete_authentication(self, pkce: PkceData, redirect_url: str) -> None:
        """Exchange the auth code from ``redirect_url`` for a token and save it.

        The PKCE state from ``pkce`` is restored on the OAuth session before
        the exchange, so it can run on any worker.
        """

        plugin = self.tidal_plugin()
        if plugin is None:
            raise RuntimeError("The Tidal plugin is not enabled.")

        session = plugin.api.session
        session._state = pkce.state
        session._code_verifier = pkce.code_verifier
        session.fetch_token(
            "https://auth.tidal.com/v1/oauth2/token",
            authorization_response=redirect_url,
            include_client_id=True,
        )
        session.save_token(session.token)


# The beets tidal plugin does not type the artwork resources, so the
# cover-related parts of its ``AlbumDocument`` are defined here.
class ArtworkFileMeta(TypedDict):
    width: int
    height: int


class ArtworkFile(TypedDict):
    href: str
    meta: ArtworkFileMeta


class ArtworkAttributes(TypedDict):
    mediaType: NotRequired[str]
    files: list[ArtworkFile]


class TidalArtwork(TypedDict):
    id: str
    type: Literal["artworks"]
    attributes: NotRequired[ArtworkAttributes]


# Anchored via `match` (start of URL), so a matching host cannot be
# smuggled in via a subdomain, path segment, or query parameter.
_TIDAL_ALBUM_URL = re.compile(
    r"https?://(?:listen\.)?tidal\.com/(?:browse/)?album/(\d+)"
)


class TidalArtSource(ArtSource):
    """Resolve album art for Tidal URLs via the authenticated Tidal API.

    The cover artwork (with file URLs for all sizes) is fetched through the
    beets tidal plugin's API; small preview sizes are returned first.
    """

    name: ClassVar[str] = "tidal"
    priority: ClassVar[int] = 10

    def matches(self, url: str) -> bool:
        return self._extract_album_id(url) is not None

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        album_id = self._extract_album_id(url)
        if album_id is None:
            return None

        # The plugin API is blocking IO (requests); keep it off the event loop.
        urls = await asyncio.to_thread(self._fetch_cover_urls, album_id)
        return ArtResult.from_urls(urls) if urls else None

    def _fetch_cover_urls(self, album_id: str) -> list[str]:
        """Return cover file URLs for a Tidal album, small previews first."""
        plugin = TidalAuth.tidal_plugin()
        if plugin is None:
            log.info("Tidal plugin not enabled; cannot fetch art for %s", album_id)
            return []

        try:
            doc = plugin.api.get_albums(ids=[album_id], include=["coverArt"])
        except Exception as err:
            log.warning("Error fetching Tidal album %s: %s", album_id, err)
            return []

        files = [
            f
            for f in self._extract_cover_files(doc)
            if f.get("href") and int(f["meta"]["width"]) >= 200
        ]
        # Smallest first (but skipping tiny thumbnails), so the art route
        # serves a cheap preview.
        return [f["href"] for f in sorted(files, key=lambda f: f["meta"]["width"])]

    @staticmethod
    def _extract_cover_files(doc: AlbumDocument) -> list[ArtworkFile]:
        """Return the cover artwork file list from an AlbumDocument, or []."""
        for included in doc.get("included", []):
            if included["type"] == "artworks":
                artwork = cast(TidalArtwork, included)
                attributes = artwork.get("attributes")
                return attributes.get("files", []) if attributes else []
        return []

    @staticmethod
    def _extract_album_id(url: str) -> str | None:
        """Return the album id from a Tidal album URL, else None."""
        match = _TIDAL_ALBUM_URL.match(url)
        return match.group(1) if match else None
