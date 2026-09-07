"""Similar to the routes/errors.py file, this file contains error handling logic for the websocket routes.

We parse all exceptions to a common format and return them to the client for handling.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import (
    TYPE_CHECKING,
    NotRequired,
    ParamSpec,
    TypedDict,
    TypeVar,
)

from beets_flask import log

from . import sio

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class WebSocketErrorDict(TypedDict):
    """Common error format for websocket routes."""

    error: str
    message: str
    description: NotRequired[str]


Params = ParamSpec("Params")
ReturnType = TypeVar("ReturnType")


def sio_catch_exception(
    func: Callable[Params, Awaitable[ReturnType]],
) -> Callable[Params, Awaitable[ReturnType | WebSocketErrorDict]]:
    """Parse exceptions to a common format for websocket routes.

    Returned functions may than return a
    WebSocketErrorDict if an exception is caught. This should
    be handled on the fronten.

    Usage
    -----
    ```python
    @sio.on("event_name", namespace="/namespace")
    @sio_catch_expection
    def event_name(sid, *args, **kwargs):
        raise Exception("Exception message")
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> ReturnType | WebSocketErrorDict:
        try:
            # Get number of arguments as socketio will not infer them correctly
            n_args = func.__code__.co_argcount
            result = await func(*args[:n_args], **kwargs)
            return result
        except Exception as e:
            return _error_parser(e)

    return wrapper


def _error_parser(e: Exception) -> WebSocketErrorDict:
    # We may add some exception handling here if
    # we want to handle some exceptions differently
    log.exception(f"Unhandled websocket error: {e}")
    d = WebSocketErrorDict(
        error=e.__class__.__name__,
        message=str(e),
    )
    return d


__all__ = ["WebSocketErrorDict", "sio_catch_exception"]


"""Allow to throw the errors in a testing
environment. This is useful for testing
the error handling on the frontend side.
"""
from . import sio


@sio.on("test_generic_exc", namespace="/test")
@sio_catch_exception
def test_generic_exc(sid):
    raise Exception("Exception message")
