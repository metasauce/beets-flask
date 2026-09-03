"""Art provider for Spotify URLs."""

from __future__ import annotations

import json
import re
from typing import ClassVar
from urllib.parse import quote_plus

import aiohttp

from beets_flask.extensions.art import ArtResult, ArtSource
from beets_flask.logger import log

# Anchored via `match` (start of URL), so a matching host cannot be
# smuggled in via a subdomain, path segment, or query parameter.
_SPOTIFY_URL = re.compile(r"https?://open\.spotify\.com/")


class SpotifyArtSource(ArtSource):
    """Resolve album art from Spotify URLs via the oembed endpoint.

    See https://developer.spotify.com/documentation/embeds/reference/oembed
    """

    name: ClassVar[str] = "spotify"
    priority: ClassVar[int] = 10
    oembed_base: ClassVar[str] = "https://embed.spotify.com/oembed"

    def matches(self, url: str) -> bool:
        return _SPOTIFY_URL.match(url) is not None

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        try:
            async with session.get(
                f"{self.oembed_base}?url={quote_plus(url)}"
            ) as response:
                if response.status != 200:
                    log.info(
                        "Spotify oembed returned status %s for %s",
                        response.status,
                        url,
                    )
                    return None
                data = await response.json()
                thumbnail_url = data.get("thumbnail_url")
                return ArtResult.from_url(thumbnail_url) if thumbnail_url else None
        except (aiohttp.ClientError, json.JSONDecodeError, TimeoutError) as err:
            log.warning("Error fetching Spotify art for %s: %s", url, err)
            return None
