"""Art extension: resolve cover art for external release URLs.

This module defines the interface implemented by art providers
(`beets_flask.extensions.providers`) and the `ArtResult` they return.
The `/art` route serves these results (see `server/routes/art_preview.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

import aiohttp


class ArtSource(ABC):
    """Interface for an art provider extension.

    Providers declare a priority used to order URL matching (a higher
    value means the source is consulted earlier). `matches` decides
    whether the source can handle a given URL, and `get_art` resolves
    the artwork using the aiohttp session provided by the caller.
    """

    name: ClassVar[str]
    priority: ClassVar[int] = 10

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Return whether this source can handle the given URL."""

    @abstractmethod
    async def get_art(
        self, url: str, session: aiohttp.ClientSession
    ) -> ArtResult | None:
        """Resolve artwork for the URL, or return None if not found."""


@dataclass(frozen=True)
class ArtResult:
    """Result of an art lookup.

    Either holds remote art URLs that still need to be fetched and proxied
    (`urls`), or image data fetched by the provider itself (`data`).
    """

    urls: list[str] = field(default_factory=list)
    data: bytes | None = None
    content_type: str | None = None

    @classmethod
    def from_url(cls, url: str) -> ArtResult:
        """Create a result pointing at a single remote art URL."""
        return cls(urls=[url])

    @classmethod
    def from_urls(cls, urls: list[str]) -> ArtResult:
        """Create a result with multiple candidate art URLs."""
        return cls(urls=urls)

    @classmethod
    def from_data(cls, data: bytes, content_type: str | None = None) -> ArtResult:
        """Create a result with the image data already fetched."""
        return cls(data=data, content_type=content_type)
