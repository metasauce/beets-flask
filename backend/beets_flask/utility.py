from .logger import log

# ------------------------------------------------------------------------------------ #
#                                         Misc                                         #
# ------------------------------------------------------------------------------------ #

# audio formats supported by beets
# https://github.com/beetbox/beets/discussions/3964
AUDIO_EXTENSIONS = (
    "mp3",
    "aac",
    "alac",
    "ogg",
    "opus",
    "flac",
    "ape",
    "wv",
    "mpc",
    "asf",
    "aiff",
    "dsf",
)


class DummyObject:
    """Object that returns None for any attribute accessed.

    You may use this. e.g. for beets.ui._load_plugin options.
    """

    def __getattr__(self, name):
        """Return None for any attribute accessed."""
        return None


# -------------------------------- Deprecation ------------------------------- #


def deprecation_warning(msg: str, alt_text: str | None = None):
    """Raises a deprecation warning in the logs."""

    msg = msg + " is deprecated and will not be supported from the v2.0.0 release."
    if alt_text:
        msg += " " + alt_text
    log.warning(msg)
