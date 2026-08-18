"""Concrete art providers.

Each module implements one `ArtSource`. This package holds the
hard-coded list of sources; a registry may replace this later.
"""

from __future__ import annotations

from .musicbrainz import MusicbrainzArtSource
from .spotify import SpotifyArtSource

# TODO: We should add a proper registry here to simplify this
# Not needed for now but once we add more parts to the extension system
# we should consider a registry to avoid hardcoding the list of providers
# and to remove the import side effect
ART_SOURCES = [
    SpotifyArtSource(),
    MusicbrainzArtSource(),
]

__all__ = [
    "ART_SOURCES",
]
