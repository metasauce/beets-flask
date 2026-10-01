"""Art provider for Bandcamp release URLs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, ClassVar

from beets_flask.extensions.art import ArtResult, ArtSource
from beets_flask.logger import log

if TYPE_CHECKING:
    import aiohttp

# Anchored via `match` (start of URL), so a matching host cannot be
# smuggled in via a subdomain, path segment, or query parameter.
_BANDCAMP_URL = re.compile(r"https?://(?:[a-z0-9-]+\.)?bandcamp\.com/", re.IGNORECASE)

# Bandcamp artwork URLs look like `.../img/a<id>_<size>.jpg`. Size 4 is a
# reasonable preview format, see https://stackoverflow.com/a/69481878.
_ARTWORK_SIZE = 4
_ARTWORK_URL_SIZE = re.compile(r"(?<=bcbits\.com/img/a)(\d+)_\d+(?=\.jpg(?:[?#]|$))")


class BandcampArtSource(ArtSource):
    """Resolve cover art from Bandcamp release pages.

    The artwork URL is extracted from the JSON-LD metadata embedded in the
    release page, following the approach used by the beetcamp plugin.
    See https://github.com/snejus/beetcamp/blob/main/beetcamp/metaguru.py
    """

    name: ClassVar[str] = "bandcamp"
    priority: ClassVar[int] = 10

    def matches(self, url: str) -> bool:
        return _BANDCAMP_URL.match(url) is not None

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        async with session.get(url) as response:
            if response.status != 200:
                log.info("Bandcamp returned status %s for %s", response.status, url)
                return None
            html = await response.text()

        match = re.search(r'.*"@id".*', html)
        if match is None:
            return None

        data = json.loads(match.group(0).strip())
        meta = data[0] if isinstance(data, list) else data
        target_meta = meta.get("inAlbum") or meta
        image = target_meta.get("image")
        if isinstance(image, list) and image:
            image = image[0]
        if not image:
            return None

        art_url = _ARTWORK_URL_SIZE.sub(rf"\g<1>_{_ARTWORK_SIZE}", str(image))
        return ArtResult.from_url(art_url)
