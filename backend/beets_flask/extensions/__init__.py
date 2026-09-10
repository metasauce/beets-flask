"""Extension framework for beets-flask.

An *extension* adds functionality to the beets-flask backend without requiring
the extension-specific code to live in the core. This keeps the core small and
focused while making it easy to add or replace functionality through
independent extensions.

Extensions typically wrap beets plugins (e.g., Spotify, MusicBrainz, etc.)
behind a common interface. This allows the backend to support optional
services without coupling its core implementation to any particular plugin.

Each extension type lives in its own module (e.g., `extensions/art.py` for
artwork resolution). The module defines an abstract base class describing the
extension interface, while concrete implementations live in
`extensions/providers/` (one module per provider).
"""

from .art import ArtResult, ArtSource
from .auth import AuthExtension, PkceData

__all__ = [
    "ArtResult",
    "ArtSource",
    "AuthExtension",
    "PkceData",
]
