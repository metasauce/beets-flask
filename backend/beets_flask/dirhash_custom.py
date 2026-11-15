from __future__ import annotations

import os
from hashlib import md5
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from re import Pattern

    from cachetools import Cache


def dirhash_c(
    dirname: str | Path,
    cache: Cache[str, bytes] | None,
    filter_regex: Pattern[str] | None = None,
) -> bytes:
    """Compute a hash for a directory.

    The hash is computed by hashing the path of each file and using
    its filesystem metadata (size, mtime, ctime).

    Parameters
    ----------
    dirname: str
        The path to the directory
    cache: dict, optional
        A cache object to store intermediate results. If None, no caching is used.
    filter_regex: re.Pattern, optional
        When calculating checksum contributon for files, only consider
        those that match the provided pattern.

    """
    if isinstance(dirname, Path):
        dirname = str(dirname.resolve())

    if cache is not None and dirname in cache:
        return cache[dirname]

    hash = md5()

    # Hash for each entry in the directory
    for entry in os.scandir(dirname):
        if entry.is_dir():
            hash.update(dirhash_c(entry.path, cache, filter_regex))
        else:
            # Skip files that do not match the filter
            if filter_regex is not None and not filter_regex.match(entry.name):
                continue

            fs = os.stat(entry.path)
            hash.update(fs.st_size.to_bytes(8, byteorder="big"))
            hash.update(fs.st_ino.to_bytes(8, byteorder="big"))
            hash.update(str(fs.st_mtime).encode())
            hash.update(entry.name.encode())

    # dirstats
    fs = os.stat(dirname)
    hash.update(dirname.encode())
    # hash.update(fs.st_size.to_bytes(8, byteorder="big"))
    # hash.update(fs.st_ino.to_bytes(8, byteorder="big"))
    # hash.update(str(fs.st_mtime).encode())

    # for dirs we should use very little info.
    # For instance, mtime, ino, size get changed when e.g. a file
    # is added directly inside - and this becomes somewhat inconsistent with
    # regex ignore patterns. (adding an ignored file would still modify the hash)

    return hash.digest()


def archive_hash(
    f_path: str | Path,
    cache: Cache[str, bytes] | None = None,
) -> bytes:
    """Compute a hash for an archive file."""

    if isinstance(f_path, Path):
        f_path = str(f_path.resolve())

    if cache is not None and f_path in cache:
        return cache[f_path]

    hash = md5()
    fs = os.stat(f_path)
    hash.update(fs.st_size.to_bytes(8, byteorder="big"))
    hash.update(fs.st_ino.to_bytes(8, byteorder="big"))
    hash.update(str(fs.st_mtime).encode())
    hash.update(os.path.basename(f_path).encode())

    if cache is not None:
        cache[f_path] = hash.digest()

    return hash.digest()


__all__ = ["archive_hash", "dirhash_c"]
