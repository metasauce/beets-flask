from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest import mock

import pytest

import beets_flask.dir_size as dir_size_module
from beets_flask.dir_size import clear_size_cache, dir_files, dir_size


@pytest.fixture(autouse=True)
def reset_walks():
    """Walks do not outlive the loop of a test."""
    dir_size_module._walks.clear()
    yield
    dir_size_module._walks.clear()


async def test_dir_size_on_first_call(tmp_path: Path):
    (tmp_path / "a.bin").write_bytes(b"x" * 5000)
    assert await dir_size(tmp_path) >= 5000


async def test_concurrent_callers_share_one_walk(tmp_path: Path, monkeypatch):
    release = asyncio.Event()
    walks = 0

    async def slow_du(path: Path) -> int:
        nonlocal walks
        walks += 1
        await release.wait()
        return 42

    monkeypatch.setattr(dir_size_module, "_du_bytes", slow_du)

    first = asyncio.create_task(dir_size(tmp_path))
    second = asyncio.create_task(dir_size(tmp_path))
    await asyncio.sleep(0)
    release.set()

    assert await first == 42
    assert await second == 42
    assert walks == 1


async def test_cancelled_caller_does_not_cancel_walk(tmp_path: Path, monkeypatch):
    release = asyncio.Event()
    walks = 0

    async def slow_du(path: Path) -> int:
        nonlocal walks
        walks += 1
        await release.wait()
        return 42

    monkeypatch.setattr(dir_size_module, "_du_bytes", slow_du)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await dir_size(tmp_path)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await dir_size(tmp_path)
    assert walks == 1  # the second caller joined the running walk

    release.set()
    assert await dir_size(tmp_path) == 42


async def test_du_total_used_on_nonzero_exit(monkeypatch):
    proc = mock.AsyncMock()
    proc.communicate.return_value = (b"123\t/x\n", b"du: cannot access '/x/y'")
    monkeypatch.setattr(
        dir_size_module.asyncio,
        "create_subprocess_exec",
        mock.AsyncMock(return_value=proc),
    )
    assert await dir_size_module._du_bytes(Path("/x")) == 123


async def test_unknown_for_missing_dir(tmp_path: Path):
    assert await dir_size(tmp_path / "does-not-exist") is None


async def test_failed_walk_returns_none_and_is_cached(tmp_path: Path, monkeypatch):
    walks = 0

    async def failing_du(path: Path) -> int:
        nonlocal walks
        walks += 1
        return -1

    monkeypatch.setattr(dir_size_module, "_du_bytes", failing_du)

    assert await dir_size(tmp_path) is None
    assert await dir_size(tmp_path) is None
    assert walks == 1  # -1 stays cached for _WALK_TTL

    clear_size_cache()
    assert await dir_size(tmp_path) is None
    assert walks == 2


async def test_finished_walk_is_reused_until_ttl(tmp_path: Path, monkeypatch):
    walks = 0

    async def du(path: Path) -> int:
        nonlocal walks
        walks += 1
        return 7

    monkeypatch.setattr(dir_size_module, "_du_bytes", du)

    assert await dir_size(tmp_path) == 7
    assert await dir_size(tmp_path) == 7
    assert walks == 1

    monkeypatch.setattr(dir_size_module, "_WALK_TTL", 0.0)
    time.sleep(0.001)
    assert await dir_size(tmp_path) == 7
    assert walks == 2


async def test_clear_size_cache_invalidates_running_walk(tmp_path: Path, monkeypatch):
    release = asyncio.Event()
    walks = 0

    async def slow_du(path: Path) -> int:
        nonlocal walks
        walks += 1
        await release.wait()
        return 42

    monkeypatch.setattr(dir_size_module, "_du_bytes", slow_du)

    first = asyncio.create_task(dir_size(tmp_path))
    await asyncio.sleep(0)
    clear_size_cache()  # the folder changed while the walk was running
    release.set()

    assert await first == 42  # the old awaiter still gets its result
    assert await dir_size(tmp_path) == 42
    assert walks == 2  # new requests do not reuse the invalidated walk


async def test_clear_size_cache_drops_known_sizes(tmp_path: Path):
    await dir_size(tmp_path)
    assert dir_size_module._walks
    clear_size_cache()
    assert not dir_size_module._walks


def test_dir_files_counts_the_directory_itself(tmp_path: Path):
    (tmp_path / "a.bin").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    assert dir_files(tmp_path) == 3


def test_dir_files_handles_paths_with_spaces(tmp_path: Path):
    folder = tmp_path / "with space"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"x")
    assert dir_files(folder) == 2
