"""Art provider for MusicBrainz release URLs."""

from __future__ import annotations

import re
from typing import ClassVar

import aiohttp

from beets_flask.extensions.art import ArtResult, ArtSource

_MUSICBRAINZ_RELEASE_PATTERN = re.compile(
    r"musicbrainz\.org/release/([0-9a-fA-F-]{36})"
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
        return _MUSICBRAINZ_RELEASE_PATTERN.search(url) is not None

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        match = _MUSICBRAINZ_RELEASE_PATTERN.search(url)
        if not match:
            return None

        release_id = match.group(1)
        return ArtResult.from_urls(
            [
                f"{self.coverart_base}/release/{release_id}/front-250",
                f"{self.coverart_base}/release/{release_id}/front",
            ]
        )
