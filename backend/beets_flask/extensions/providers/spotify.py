"""Art provider for Spotify URLs."""

from __future__ import annotations

import json
from typing import ClassVar
from urllib.parse import quote_plus

import aiohttp

from beets_flask.extensions.art import ArtResult, ArtSource
from beets_flask.logger import log


class SpotifyArtSource(ArtSource):
    """Resolve album art from Spotify URLs via the oembed endpoint.

    See https://developer.spotify.com/documentation/embeds/reference/oembed
    """

    name: ClassVar[str] = "spotify"
    priority: ClassVar[int] = 10
    oembed_base: ClassVar[str] = "https://embed.spotify.com/oembed"

    def matches(self, url: str) -> bool:
        return url.startswith("https://open.spotify.com/")

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        try:
            async with session.get(
                f"{self.oembed_base}?url={quote_plus(url)}"
            ) as response:
                if response.status != 200:
                    log.error(f"Error fetching Spotify art: {response.status}")
                    return None
                data = await response.json()
                thumbnail_url = data.get("thumbnail_url")
                return ArtResult.from_url(thumbnail_url) if thumbnail_url else None
        except (aiohttp.ClientError, json.JSONDecodeError) as err:
            log.error(f"Error fetching Spotify art for {url}: {err}")
            return None
