"""Tests for the shared `du` walk cache.

The stats endpoints depend on three things: one walk per path, a walk that
outlives a request timeout, and a cache that can be invalidated. Each test below
covers one of them.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest

import beets_flask.dir_size as dir_size_module
from beets_flask.dir_size import clear_size_cache, dir_files, dir_size


@dataclass
class DuStub:
    """Stand-in for the `du` subprocess."""

    calls: list[Path]
    release: asyncio.Event
    result: int = 42  # what `du -sb` prints; -1 is the failure sentinel

    async def __call__(self, path: Path) -> int:
        self.calls.append(path)
        await self.release.wait()
        return self.result


@pytest.fixture(autouse=True)
def reset_walks():
    """Walks are module state bound to an event loop, so do not leak them."""
    dir_size_module._walks.clear()
    yield
    dir_size_module._walks.clear()


@pytest.fixture
def du(monkeypatch) -> DuStub:
    """Replace `du` with a stub that returns 42 unless `du.release` is cleared."""
    stub = DuStub(calls=[], release=asyncio.Event())
    stub.release.set()
    monkeypatch.setattr(dir_size_module, "_du_bytes", stub)
    return stub


@pytest.mark.parametrize("existing", [True, False])
async def test_dir_size_with_the_real_du(tmp_path: Path, existing: bool):
    """The real binary must work as called: a total for an existing folder, None
    when `du` prints nothing (missing folder, empty stdout)."""
    path = tmp_path / "walk"
    if existing:
        path.mkdir()
        (path / "a.bin").write_bytes(b"x" * 5000)

    size = await dir_size(path)

    if existing:
        assert size is not None
        assert size >= 5000
    else:
        assert size is None


async def test_du_total_is_used_when_du_reports_errors(monkeypatch):
    """`du` exits nonzero on unreadable files inside a folder but still prints a
    usable total; that total is what gets shown."""
    proc = mock.AsyncMock()
    proc.communicate.return_value = (b"123\t/x\n", b"du: cannot access '/x/y'")
    monkeypatch.setattr(
        dir_size_module.asyncio,
        "create_subprocess_exec",
        mock.AsyncMock(return_value=proc),
    )

    assert await dir_size_module._du_bytes(Path("/x")) == 123


async def test_slow_walk_is_shared_and_survives_a_caller_timeout(tmp_path: Path, du):
    """A second request joins the running walk instead of starting another, and
    the stats deadline (2 s in the endpoints) cancels the request, not the walk."""
    du.release.clear()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await dir_size(tmp_path)

    other = asyncio.create_task(dir_size(tmp_path))
    du.release.set()

    assert await other == 42
    assert len(du.calls) == 1


@pytest.mark.parametrize(("result", "expected"), [(42, 42), (-1, None)])
async def test_walk_result_is_cached_until_cleared(
    tmp_path: Path, du, result: int, expected: int | None
):
    """Later requests reuse the finished walk, and a failed walk (`du` returning
    -1) is exposed as None but cached the same way. Only `clear_size_cache`
    forces a new walk, because walking a network mount on every poll is worse
    than a stale value."""
    du.result = result

    assert await dir_size(tmp_path) == expected
    assert await dir_size(tmp_path) == expected
    assert len(du.calls) == 1

    clear_size_cache()
    assert await dir_size(tmp_path) == expected
    assert len(du.calls) == 2


async def test_finished_walk_expires(tmp_path: Path, du, monkeypatch):
    """The TTL keeps a size from being reused forever on a server that never gets
    a filesystem event for the folder."""
    monkeypatch.setattr(dir_size_module, "_WALK_TTL", 0.0)

    assert await dir_size(tmp_path) == 42
    time.sleep(0.001)
    assert await dir_size(tmp_path) == 42
    assert len(du.calls) == 2


async def test_clear_size_cache_does_not_reuse_a_running_walk(tmp_path: Path, du):
    """Deleting or uploading a folder clears the cache while a walk may still be
    running. That walk still answers its caller, but nobody gets its stale
    result afterwards."""
    du.release.clear()

    first = asyncio.create_task(dir_size(tmp_path))
    await asyncio.sleep(0)
    clear_size_cache()
    du.release.set()

    assert await first == 42
    assert await dir_size(tmp_path) == 42
    assert len(du.calls) == 2


@pytest.mark.parametrize("name", ["plain", "with space"])
def test_dir_files_counts_entries(tmp_path: Path, name: str):
    """`dir_files` runs `find` without a shell, so paths with spaces work. The
    count includes the folder itself, same as the old `find | wc -l`."""
    folder = tmp_path / name
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"x")

    assert dir_files(folder) == 2
