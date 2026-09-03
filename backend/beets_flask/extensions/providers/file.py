import asyncio
import os
from typing import ClassVar

import aiohttp
from mediafile import MediaFile

from beets_flask.extensions.art import ArtResult, ArtSource
from beets_flask.utility import AUDIO_EXTENSIONS


class FileArtSource(ArtSource):
    """Infer the folder art from a given ``file://`` path.

    This is a bit of a hack, but it works for now. The first audio file in
    the folder is checked for embedded cover art, which is returned
    directly as image data.
    """

    name: ClassVar[str] = "file"
    priority: ClassVar[int] = 10

    def matches(self, url: str) -> bool:
        return url.startswith("file://")

    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        # MediaFile parsing is blocking IO; keep it off the event loop.
        return await asyncio.to_thread(self._get_art, url.removeprefix("file://"))

    def _get_art(self, path: str) -> ArtResult | None:
        if not os.path.isdir(path):
            return None

        files = sorted(
            f
            for f in os.listdir(path)
            if f.endswith(tuple(f".{ext}" for ext in AUDIO_EXTENSIONS))
        )
        if not files:
            return None

        mediafile = MediaFile(os.path.join(path, files[0]))
        images = mediafile.images
        if not images:
            return None

        image = images[0]
        return ArtResult.from_data(image.data, image.mime_type)
