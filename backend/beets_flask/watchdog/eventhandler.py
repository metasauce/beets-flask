"""Async event handler for watchdog.

Adapted from https://github.com/biesnecker/hachiko/blob/master/hachiko/hachiko.py
MIT License
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileClosedEvent,
    FileClosedNoWriteEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from beets_flask import log

EVENT_TYPE_MOVED = "moved"
EVENT_TYPE_DELETED = "deleted"
EVENT_TYPE_CREATED = "created"
EVENT_TYPE_MODIFIED = "modified"
EVENT_TYPE_CLOSED = "closed"
EVENT_TYPE_OPENED = "opened"
EVENT_TYPE_CLOSED_NO_WRITE = "closed_no_write"


class AIOEventHandler:
    """An asyncio-compatible event handler."""

    def __init__(self, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self._ensure_future = asyncio.create_task
        self._method_map: dict[str, Callable] = {
            EVENT_TYPE_MODIFIED: self.on_modified,
            EVENT_TYPE_MOVED: self.on_moved,
            EVENT_TYPE_CREATED: self.on_created,
            EVENT_TYPE_DELETED: self.on_deleted,
            EVENT_TYPE_CLOSED: self.on_closed,
            EVENT_TYPE_OPENED: self.on_opened,
            EVENT_TYPE_CLOSED_NO_WRITE: self.on_closed_no_write,
        }

    async def on_any_event(self, event: FileSystemEvent):
        raise NotImplementedError

    async def on_moved(self, event: DirMovedEvent | FileMovedEvent):
        pass

    async def on_created(self, event: DirCreatedEvent | FileCreatedEvent):
        pass

    async def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent):
        pass

    async def on_modified(self, event: DirModifiedEvent | FileModifiedEvent):
        pass

    async def on_closed(self, event: FileClosedEvent):
        pass

    async def on_closed_no_write(self, event: FileClosedNoWriteEvent):
        pass

    async def on_opened(self, event: FileOpenedEvent):
        pass

    def dispatch(self, event: FileSystemEvent):
        handler = self._method_map[event.event_type]
        self._loop.call_soon_threadsafe(self._ensure_future, self.on_any_event(event))
        self._loop.call_soon_threadsafe(self._ensure_future, handler(event))


class AIOWatchdog:
    def __init__(
        self,
        paths: list[Path],
        handler: AIOEventHandler,
        recursive=True,
        observer: BaseObserver | None = None,
    ):
        if observer is None:
            self._observer = Observer()
        else:
            self._observer = observer

        self._handler = handler

        for path in paths:
            if not path.exists():
                log.warning(
                    f"Path does not exist: {path}. Check your configuration or create it."
                )
                continue
            if not path.is_dir() and not path.is_file():
                log.warning(
                    f"Path is neither a file nor a directory: {path}. Check your configuration."
                )
                continue
            log.debug(f"Adding path to watchdog: {path} (recursive={recursive})")
            self._observer.schedule(
                cast(FileSystemEventHandler, self._handler),
                path=str(path.resolve()),
                recursive=recursive,
            )

    def start(self):
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()
