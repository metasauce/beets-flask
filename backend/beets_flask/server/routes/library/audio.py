"""File streaming as mp3.

Allows to stream an item's file as mp3.
"""

import asyncio
import os
import time
from asyncio.subprocess import PIPE, Process
from collections.abc import AsyncIterator, Hashable
from typing import TYPE_CHECKING, Any, TypeVar

import aiofiles
import numpy as np
from cachetools import Cache, TTLCache
from cachetools.keys import hashkey
from quart import Blueprint, Response, g

from beets_flask.logger import log
from beets_flask.server.exceptions import IntegrityException, NotFoundException
from beets_flask.server.routes.library.path_utils import resolve_library_path

audio_bp = Blueprint("audio", __name__)

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g


transcodeCache: Cache[Hashable, Any] = TTLCache(
    maxsize=128, ttl=60 * 60
)  # 1 hour cache
peaksCache: Cache[Hashable, Any] = TTLCache(maxsize=128, ttl=60 * 60)  # 1 hour cache


@audio_bp.route("/item/<int:item_id>/audio", methods=["GET"])
async def item_audio(item_id: int):
    """Get the raw item data.

    For streaming the audio file directly to the client.
    """
    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:'{item_id}' not found in beets db."
        )

    item_path = resolve_library_path(item.path)
    if not os.path.exists(item_path):
        raise IntegrityException(
            f"Item file '{item_path}' does not exist for item beets_id:'{item_id}'."
        )

    it = await transcode_to_webm(item_path)
    return Response(
        cached_async_iterator(item_path, it, transcodeCache),
        mimetype="audio/webm",
    )


@audio_bp.route("/item/<int:item_id>/audio/peaks", methods=["GET"])
async def item_audio_peaks(item_id: int):
    """Get the raw item data.

    For streaming the audio file directly to the client.
    """
    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:'{item_id}' not found in beets db."
        )

    item_path = resolve_library_path(item.path)
    if not os.path.exists(item_path):
        raise IntegrityException(
            f"Item file '{item_path}' does not exist for item beets_id:'{item_id}'."
        )

    peaks = await audio_peaks_cached(item_path)
    return Response(
        peaks.tobytes(),
        mimetype="application/octet-stream",
    )


class FFmpegError(RuntimeError):
    def __init__(self, returncode: int, stderr: str):
        super().__init__(f"FFmpeg failed with code {returncode}: {stderr.strip()}")
        self.returncode = returncode
        self.stderr = stderr


FATAL_PATTERNS = ["Error", "Invalid data", "partial file", "Could not"]


class FFmpegStreamer:
    """A class to handle streaming audio files through FFmpeg.

    This class initializes a persistent FFmpeg process and streams audio files
    through it. It uses asyncio for asynchronous I/O operations.
    The FFmpeg process is started with the specified arguments and the input
    is written to its stdin. The output is read from its stdout in chunks.
    """

    process: Process | None
    _stderr_lines: list[str] = []
    chunk_size: int = 4096

    def __init__(self):
        self.process = None

    async def start(self, *ffmpeg_args):
        """Initialize a persistent FFmpeg process with stdin open for input."""
        self._stderr_lines = []
        self.process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            *ffmpeg_args,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )
        asyncio.create_task(self._drain_stderr())

    async def stream_file(self, file_path: str | None) -> AsyncIterator[bytes]:
        """Stream an audio file through the pre-warmed FFmpeg process.

        If file_path is None, it will just stream from the existing process.
        """

        if (
            self.process is None
            or self.process.stdin is None
            or self.process.stdout is None
        ):
            raise RuntimeError("FFmpeg process not started. Call start() first.")

        if file_path is not None and os.path.exists(file_path):
            writer = asyncio.create_task(
                self._write_input(self._file_chunker(file_path))
            )
        else:
            writer = None

        start = time.process_time_ns()
        try:
            while not self.process.stdout.at_eof():
                chunk = await self.process.stdout.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            if writer is not None:
                await writer
            return_code = await self.process.wait()
            if return_code != 0 or self._stderr_lines:
                raise FFmpegError(return_code, "".join(self._stderr_lines))

            end = time.process_time_ns()
            log.debug(f"Transcoded {file_path} in {(end - start) / 1_000_000_000:.2f}s")

    async def stream(self) -> AsyncIterator[bytes]:
        """Stream audio data from the FFmpeg process."""
        if (
            self.process is None
            or self.process.stdin is None
            or self.process.stdout is None
        ):
            raise RuntimeError("FFmpeg process not started. Call start() first.")

        start = time.process_time_ns()
        try:
            while not self.process.stdout.at_eof():
                chunk = await self.process.stdout.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            return_code = await self.process.wait()
            if return_code != 0 or self._stderr_lines:
                raise FFmpegError(return_code, "".join(self._stderr_lines))

            end = time.process_time_ns()
            log.info(f"Streamed in {(end - start) / 1_000_000_000:.2f} s")

    async def _drain_stderr(self):
        """Continuously read and print FFmpeg stderr."""
        assert self.process and self.process.stderr
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break

            decoded = line.decode().strip()
            self._stderr_lines.append(decoded)
            log.error(f"FFmpeg stderr: {decoded}")

    async def _write_input(self, input_stream: AsyncIterator[bytes]):
        assert self.process is not None
        assert self.process.stdin is not None

        async for data in input_stream:
            self.process.stdin.write(data)
            await self.process.stdin.drain()
        self.process.stdin.close()

    async def _file_chunker(
        self, path: str, size: int = 64 * 1024
    ) -> AsyncIterator[bytes]:
        # Use a semaphore to control read-ahead and prevent memory bloat
        semaphore = asyncio.Semaphore(size * 100)

        try:
            async with aiofiles.open(path, "rb") as file:
                while True:
                    await semaphore.acquire()
                    chunk = await file.read(size)
                    if chunk == b"":
                        break
                    yield chunk
                    semaphore.release()

                log.warning(f"Finished reading file {path}")

        except asyncio.CancelledError:
            log.info(f"File reading cancelled for {path}")
            raise
        except Exception as e:
            log.error(f"Error reading file {path}: {e}")
            raise


T = TypeVar("T")


async def cached_async_iterator(
    key: Hashable, iterator: AsyncIterator[T], cache: Cache[Hashable, list[T]]
) -> AsyncIterator[T]:
    """Cache the results of an async iterator."""
    try:
        cached = []
        if key in cache:
            log.debug(f"Using cached data for {key}")
            cached = cache[key]
        else:
            log.debug(f"Caching data for {key}")
            async for item in iterator:
                cached.append(item)
                yield item

            cache[key] = cached
            return

        for item in cached:
            yield item
    except Exception:
        cache.pop(key, None)
        raise


STREAMABLE_FORMATS = {"wav", "flac", "ogg", "pcm"}  # extend if needed
CONTAINER_FORMATS = {"m4a", "mp4", "mov", "alac", "aac", "mp3"}  # require seek


async def transcode_to_webm(file_path: str) -> AsyncIterator[bytes]:
    """Transcode a file to mp3 using FFmpeg and stream it."""
    ffmpeg_streamer = FFmpegStreamer()
    ext = file_path.split(".")[-1].lower()

    # This yields quite fast transcoding
    # for me, might need a bit more benchmarking
    # fmt: off
    if ext in STREAMABLE_FORMATS:
        await ffmpeg_streamer.start(*[
            "-hide_banner",
            "-loglevel", "error",
            "-fflags", "nobuffer",
            "-flush_packets", "0",
            "-probesize", "32",
            "-f", ext, "-i", "-",               # stdin input
            "-vn", "-sn", "-dn",                # DROP video streams
            "-preset", "ultrafast",             # Faster MP3 encoding
            "-map_metadata", "-1",              # Skip all metadata
            "-map", "0:a",                      # Map all audio streams
            "-codec:a", "libopus",
            "-b:a", "128k",
            "-f", "webm",                        # Force MP3 format for stdout
            "-",                                # Output to stdout
        ])
        # fmt: on
        return ffmpeg_streamer.stream_file(file_path)
    else:
        await ffmpeg_streamer.start(*[
            "-hide_banner",
            "-loglevel", "error",
            "-fflags", "nobuffer",
            "-flush_packets", "0",
            "-probesize", "32",
            "-i", str(file_path),               # file input
            "-vn", "-sn", "-dn",                # DROP video streams
            "-preset", "ultrafast",             # Faster MP3 encoding
            "-map_metadata", "-1",              # Skip all metadata
            "-map", "0:a",                      # Map all audio streams
            "-codec:a", "libopus",
            "-b:a", "128k",
            "-f", "webm",                        # Force MP3 format for stdout
            "-",                                # Output to stdout
        ])
    return ffmpeg_streamer.stream_file(file_path)


peaksCache = TTLCache(maxsize=128, ttl=60 * 60)  # 1 hour cache


async def audio_peaks_cached(item_path: str) -> np.ndarray:
    """Helper function with LRU caching."""
    cache_key = hashkey(item_path)
    if cache_key in peaksCache:
        log.debug(f"Using cached peaks for {item_path}")
        return peaksCache[cache_key]

    result = await audio_peaks(item_path)
    peaksCache[cache_key] = result
    return result


async def audio_peaks(path: str):
    ffmpeg_streamer = FFmpegStreamer()

    # fmt: off
    await ffmpeg_streamer.start(*[
        "-hide_banner",
        "-loglevel", "error",
        '-i', str(path),
        '-ac', "1",
        '-filter:a', 'aresample=8000',
        '-map','0:a',
        '-c:a',
        'pcm_s16le',
        '-f', 'data',       # Signed 16-bit little-endian PCM
        '-'
    ])
    # fmt: on

    # Convert to numpy array
    raw_samples = b"".join([chunk async for chunk in ffmpeg_streamer.stream()])
    # Normalize to -1.0 to 1.0 range
    samples = np.frombuffer(raw_samples, dtype=np.int16).astype(np.float32) / 32768.0
    # Downsample
    window_size = 2056
    starts = np.arange(0, samples.shape[0], window_size)
    maxs = np.maximum.reduceat(samples, starts, dtype=np.float32)
    return maxs


async def chunked_bytes_iterator(
    data: bytes, chunk_size: int = 8192
) -> AsyncIterator[bytes]:
    """
    Async iterator that yields chunks of bytes data.

    Args:
        data: The bytes object to be chunked
        chunk_size: Size of each chunk in bytes (default: 8KB)
    """
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]
