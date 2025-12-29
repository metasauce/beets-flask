import io
import sys

from deprecated import deprecated

from .logger import log

# ------------------------------------------------------------------------------------ #
#                                        Logging                                       #
# ------------------------------------------------------------------------------------ #


@deprecated
def capture_stdout_stderr(func, *args, **kwargs):
    """
    beets.ui uses a custom `print_` function to display most console output in a nicely formatted way. This is the easiest way to capture that output.

    Args:
        func (callable): function to call
        *args: positional arguments to pass to `func`
        **kwargs: keyword arguments to pass to `func`

    Returns
    -------
        tuple: (str, str, any) -- stdout, stderr, return value of `func`
    """
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    buf_stdout = io.StringIO()
    buf_stderr = io.StringIO()
    sys.stdout = buf_stdout
    sys.stderr = buf_stderr
    try:
        res = func(*args, **kwargs)
    except Exception as ep:
        log.error(ep, exc_info=True)
        res = None
    sys.stdout.flush()
    sys.stderr.flush()
    sys.stdout = original_stdout
    sys.stderr = original_stderr
    return buf_stdout.getvalue(), buf_stderr.getvalue(), res


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
