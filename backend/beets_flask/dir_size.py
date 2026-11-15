"""Sizes and file counts for library and inbox folders.

`du` is slow on large or network-mounted folders, so each path has at most one
running `du` task per process. Concurrent requests share that task. Cancelling a
request does not cancel the shared walk.

This assumes one event loop per process.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from typing import TYPE_CHECKING

from cachetools import TTLCache, cached

from beets_flask.logger import log

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["clear_size_cache", "dir_files", "dir_size"]

_WALK_TTL = 3600.0  # seconds a finished walk stays reusable, from its start

# path -> (shared du task, walk start time)
_walks: dict[Path, tuple[asyncio.Task[int], float]] = {}


async def _du_bytes(path: Path) -> int:
    """Run `du -sb`; return -1 if no total could be obtained."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "du",
            "-sb",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        # `du` may exit nonzero if files disappear during the walk, but can
        # still print a usable total.
        return int(stdout.split()[0])
    except Exception as exc:
        log.error("Could not determine size of %s: %s", path, exc)
        return -1


async def dir_size(path: Path) -> int | None:
    """Size of a directory in bytes, including its contents.

    Returns `None` if the walk fails. Cancelling the caller leaves the shared
    walk running for other callers.
    """
    key = path.resolve()
    now = time.monotonic()

    entry = _walks.get(key)
    if entry is None or (entry[0].done() and now - entry[1] > _WALK_TTL):
        task = asyncio.create_task(_du_bytes(key))
        entry = (task, now)
        _walks[key] = entry

    # Shield the shared task: cancelling this request must not cancel the walk
    # that other requests are awaiting.
    result = await asyncio.shield(entry[0])
    return result if result >= 0 else None


@cached(cache=TTLCache(maxsize=1024, ttl=60), info=True)
def dir_files(path: Path) -> int:
    """Count entries below a directory, including the directory itself."""
    try:
        result = subprocess.run(
            ["find", str(path.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        return len(result.stdout.splitlines())
    except Exception as exc:
        log.error("Could not count entries in %s: %s", path, exc)
        return -1


def clear_size_cache() -> None:
    """Invalidate cached sizes and file counts.

    Running walks are removed from `_walks` on purpose: their existing awaiters
    still receive their result, but new requests start a fresh walk.
    """
    _walks.clear()
    dir_files.cache.clear()  # type: ignore
