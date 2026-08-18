"""Extension framework for beets-flask.

An *extension* wraps an external service (typically a beets plugin, e.g.
spotify, musicbrainz, ...) behind a common interface so
that beets-flask can use it without depending on the service directly.

Each extension kind lives in its own module (`extensions/art.py` for art
resolution) and declares an abstract base class plus a set of concrete
implementations in `extensions/providers/<extension_name>`.
"""
