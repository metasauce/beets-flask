"""Allows the client to listen to status updates from the server.

Status updates are mainly send after a successful import or when
a preview is finished.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Concatenate, Literal, ParamSpec, TypeVar

import socketio
from quart import json

from beets_flask.database import db_session_factory
from beets_flask.database.models.states import FolderInDb
from beets_flask.disk import clear_cache
from beets_flask.importer.progress import FolderStatus
from beets_flask.invoker.job import JobMeta
from beets_flask.logger import log
from beets_flask.server.exceptions import (
    InvalidUsageException,
    SerializedException,
    to_serialized_exception,
)

from . import sio
from .errors import sio_catch_exception

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from beets_flask.invoker.job import JobMeta


@dataclass
class JobStatusUpdate:
    message: str
    num_jobs: int
    job_metas: list[JobMeta]
    exc: SerializedException | None = None
    event: Literal["job_status_update"] = "job_status_update"


@dataclass
class FolderStatusUpdate:
    path: str
    hash: str
    status: FolderStatus
    exc: SerializedException | None = None
    event: Literal["folder_status_update"] = "folder_status_update"


@dataclass
class FileSystemUpdate:
    exc: SerializedException | None = None
    event: Literal["file_system_update"] = "file_system_update"


namespace = "/status"


@sio.on("connect", namespace=namespace)
@sio_catch_exception
async def connect(sid, *args):
    """Log connection."""
    log.debug(f"StatusSocket sid {sid} connected")


# ---------------------------- Emit to all clients --------------------------- #


@sio.on("folder_status_update", namespace=namespace)
@sio_catch_exception
async def folder_update(sid, data):
    log.debug(f"folder_status_update: {data}")
    await sio.emit("folder_status_update", data, namespace=namespace)


@sio.on("job_status_update", namespace=namespace)
@sio_catch_exception
async def job_update(sid, data):
    log.debug(f"job_status_update: {data}")
    await sio.emit("job_status_update", data, namespace=namespace)


@sio.on("file_system_update", namespace=namespace)
@sio_catch_exception
async def fs_update(sid, data):
    log.debug(f"file_system_update: {data}")
    clear_cache()
    await sio.emit("file_system_update", data, namespace=namespace)


# ------------------------------------- * ------------------------------------ #


@sio.on("*", namespace=namespace)
@sio_catch_exception
async def any_event(event, sid, data):
    """Debug unhandled events."""
    log.debug(f"StatusSocket sid {sid} unhandled event {event} with data {data}")


async def send_status_update(
    status: FolderStatusUpdate | JobStatusUpdate | FileSystemUpdate,
):
    """Send a status update to propagate to all clients.

    Allows to pass an exception as part of the status update.
    This is used when a preview fails, i.e. FolderStatus.FAILED
    """

    # We use a simple client here as this code may be called from
    # redis workers which do not have access to the sio instance.
    # See /status/update sio endpoint above for how this is handled
    # on the server.
    # By providing the json module via quart, we reuse our custom json encoder.
    client = socketio.AsyncClient(json=json)
    # FIXME: Static URL is difficult to maintain and testing does not work
    # with this setup. We need to find a way to make this dynamic.
    await client.connect("ws://127.0.0.1:5001", namespaces=[namespace])

    # We need to use call (instead of emit) as otherwise the event is not emitted
    # if we close the client immediately after connecting
    await client.call(
        status.event,
        status,
        namespace=namespace,
        timeout=5,
    )
    await client.disconnect()


async def trigger_clear_cache():
    """Trigger a cache clear via the status socket."""
    # This is used to clear the cache when a folder is deleted.
    # We use the FileSystemUpdate event to trigger this.
    # This clears the cache in all workers and clients
    clear_cache()
    await send_status_update(FileSystemUpdate())


R = TypeVar("R")  # Return
P = ParamSpec("P")  # Parameters


def emit_folder_status(
    before: FolderStatus | None = None, after: FolderStatus | None = None
) -> Callable[
    [Callable[Concatenate[str, str, P], Awaitable[R]]],
    Callable[Concatenate[str, str | None, P], Awaitable[R]],
]:
    """Decorator to propagate status updates to clients.

    Parameters
    ----------
    before: FolderStatus, optional
        The status before the function is called. If none is given, no status update is sent.
    after: FolderStatus, optional
        The status after the function is called. If none is given, no status update is sent.

    """

    def decorator(
        f: Callable[Concatenate[str, str, P], Awaitable[R]],
    ) -> Callable[Concatenate[str, str | None, P], Awaitable[R]]:
        @wraps(f)
        async def wrapper(hash: str, path: str | None, *args, **kwargs) -> R:
            # if only a hash is given and no path, we retrieve the path from the db
            if path is None:
                with db_session_factory() as db_session:
                    f_on_disk = FolderInDb.get_by(
                        FolderInDb.id == hash, session=db_session
                    )
                    if f_on_disk is None:
                        raise InvalidUsageException(
                            "If only hash is given, it must be in the db."
                        )
                    path = f_on_disk.full_path

            # FIXME: In theory we could keep the socket client open here
            if before is not None:
                await send_status_update(
                    FolderStatusUpdate(
                        hash=hash,
                        path=path,
                        status=before,
                    )
                )

            try:
                ret = await f(hash, path, *args, **kwargs)
            except Exception as e:
                # if the function fails, we want to send a failed status update
                # and raise the exception again.
                await send_status_update(
                    FolderStatusUpdate(
                        hash=hash,
                        path=path,
                        status=FolderStatus.FAILED,
                        exc=to_serialized_exception(e),
                    )
                )

                raise e

            if after is not None:
                await send_status_update(
                    FolderStatusUpdate(
                        hash=hash,
                        path=path,
                        status=after,
                    )
                )

            return ret

        return wrapper

    return decorator


def register_status():
    # we need this to at least allow loading the module at the right time
    pass
