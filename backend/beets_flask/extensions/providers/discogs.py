"""Art provider for Discogs release URLs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from confuse import ConfigError

from beets_flask.config import get_config
from beets_flask.extensions.art import ArtResult, ArtSource
from beets_flask.logger import log

if TYPE_CHECKING:
    import aiohttp

# Anchored via `match` (start of URL), so a matching host cannot be
# smuggled in via a subdomain, path segment, or query parameter.
_DISCOGS_RELEASE_URL = re.compile(
    r"https?://(?:www\.)?discogs\.com(?::\d+)?"
    r"/(?:[^/?#]+/)?release/(\d+)(?:-[^/?#]*)?/?(?:[?#]|$)",
    re.IGNORECASE,
)


class DiscogsArtSource(ArtSource):
    """Resolve cover art for Discogs release URLs via the Discogs API.

    See https://www.discogs.com/developers

    The API allows unauthenticated lookups with a lower rate limit. A
    configured ``discogs.user_token`` (from the beets discogs plugin) is
    sent when present to raise that limit, but is not required.
    """

    name: ClassVar[str] = "discogs"
    priority: ClassVar[int] = 10
    api_base: ClassVar[str] = "https://api.discogs.com"

    def matches(self, url: str) -> bool:
        return _release_id(url) is not None

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        release_id = _release_id(url)
        if release_id is None:
            return None

        token = _user_token()
        headers = {"Authorization": f"Discogs token={token}"} if token else {}

        async with session.get(
            f"{self.api_base}/releases/{release_id}", headers=headers
        ) as response:
            if response.status != 200:
                log.info(
                    "Discogs API returned status %s for release %s",
                    response.status,
                    release_id,
                )
                return None
            data = await response.json()

        images = data.get("images", [])
        if not images:
            return None

        # The first image is the primary cover.
        # `uri150` is a small thumbnail
        image = images[0]
        candidates = [
            candidate
            for candidate in (image.get("uri150"), image.get("uri"))
            if isinstance(candidate, str) and candidate
        ]
        return ArtResult.from_urls(candidates) if candidates else None


def _release_id(url: str) -> str | None:
    """Return the release id for a Discogs release URL, else None."""
    match = _DISCOGS_RELEASE_URL.match(url)
    return match.group(1) if match else None


def _user_token() -> str:
    """Return the configured beets discogs user token, or an empty string."""
    try:
        return get_config().beets_config["discogs"]["user_token"].as_str()
    except ConfigError:
        return ""
