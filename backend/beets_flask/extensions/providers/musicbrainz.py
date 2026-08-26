"""Art provider for MusicBrainz release URLs."""

from __future__ import annotations

import re
from typing import ClassVar

import aiohttp

from beets_flask.extensions.art import ArtResult, ArtSource

_MUSICBRAINZ_RELEASE_URL = re.compile(
    r"https?://musicbrainz\.org/release/([0-9a-fA-F-]{36})"
)


class MusicbrainzArtSource(ArtSource):
    """Resolve cover art for MusicBrainz release URLs.

    See https://musicbrainz.org/doc/Cover_Art_Archive/API

    The smaller `front-250` thumbnail is tried first, with the full-size
    `front` image as a fallback candidate.
    """

    name: ClassVar[str] = "musicbrainz"
    priority: ClassVar[int] = 10
    coverart_base: ClassVar[str] = "https://coverartarchive.org"

    def matches(self, url: str) -> bool:
        return _release_id(url) is not None

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        release_id = _release_id(url)
        if release_id is None:
            return None

        return ArtResult.from_urls(
            [
                f"{self.coverart_base}/release/{release_id}/front-250",
                f"{self.coverart_base}/release/{release_id}/front",
            ]
        )


def _release_id(url: str) -> str | None:
    """Return the release MBID for a ``musicbrainz.org`` release URL, else None."""
    match = _MUSICBRAINZ_RELEASE_URL.match(url)
    return match.group(1) if match else None
