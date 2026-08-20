from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import cache
from pathlib import Path
from typing import (
    Literal,
)

from beets.importer.tasks import MULTIDISC_PATTERNS, albums_in_dir
from beets.util import bytestring_path
from cachetools import Cache, TTLCache, cached
from natsort import os_sorted

from beets_flask.config import get_config
from beets_flask.dirhash_custom import archive_hash, dirhash_c
from beets_flask.logger import log
from beets_flask.utility import AUDIO_EXTENSIONS

# Regex pattern to exclude hidden files (files starting with ".")
audio_regex = re.compile(
    r".*\.(" + "|".join(AUDIO_EXTENSIONS) + ")$",
    re.IGNORECASE,
)


@dataclass
class FileSystemItem(ABC):
    """Base class for file system items."""

    type: Literal["file", "directory", "archive"]
    full_path: str
    hash: str

    # If beets has marked this folder as an album, or, if its a file, archives can be
    # imported. Singletons (importing music files directly) is not supported yet.
    is_album: bool

    @property
    def path(self) -> Path:
        # For convenience, to get `full_path` as a Path object,
        # but in the frontend and sqlite database, we use strings (full_path).
        return Path(self.full_path)

    @path.setter
    def path(self, value: Path) -> None:
        self.full_path = str(value)

    @classmethod
    @abstractmethod
    def from_path(
        cls, path: Path | str, cache: Cache[str, bytes] | None = None
    ) -> FileSystemItem:
        """Create a FileSystemItem object from a path."""
        raise NotImplementedError("This method should be implemented in subclasses.")


def fs_item_from_path(
    path: Path | str, cache: Cache[str, bytes] | None = None, subdirs: bool = True
) -> File | Folder | Archive:
    """Create a _specific_ FileSystemItem from a path."""
    if isinstance(path, str):
        path = Path(path)

    if path.is_dir():
        return Folder.from_path(path, cache=cache, subdirs=subdirs)
    elif is_archive_file(path):
        return Archive.from_path(path, cache=cache)
    else:
        return File.from_path(path, cache=cache)


def _matches_patterns(s: str, patterns: list[str]) -> bool:
    """Check if a string matches any of the given patterns."""
    return any(fnmatch(s, pat) for pat in patterns)


@dataclass
class Folder(FileSystemItem):
    children: Sequence[FileSystemItem]

    def __init__(
        self,
        children: Sequence[FileSystemItem],
        full_path: str,
        hash: str,
        is_album: bool = False,
    ):
        super().__init__(
            full_path=full_path,
            hash=hash,
            is_album=is_album,
            type="directory",
        )
        self.children = children

    @classmethod
    def from_path(
        cls,
        path: Path | str,
        cache: Cache[str, bytes] | None = None,
        subdirs=True,
    ) -> Folder:
        """Create a Folder object from a path."""

        ignore_globs = get_config().ignore_globs

        if isinstance(path, str):
            path = Path(path)

        if not path.is_dir():
            raise FileNotFoundError(f"Path `{path}` does not exist or is no directory.")

        path = path.resolve()

        album_folders = all_album_folders(path, subdirs=subdirs)

        # Cache for the dirhash function
        if cache is None:
            cache = Cache(maxsize=2**16)

        # Object that contains all tree elements, because
        # we need to fill top down but iterate buttom up
        lookup: dict[str, Folder] = dict()

        # Iterate over all directories from bottom to top
        for dirpath, dirnames, filenames in os.walk(path, topdown=False):
            if _matches_patterns(os.path.basename(dirpath), ignore_globs):
                continue

            # Skip ignored files
            # TODO: I think we could optimize this by
            # compiling to regex
            _dirnames = filter(
                lambda d: not _matches_patterns(d, ignore_globs), dirnames
            )
            _filenames = filter(
                lambda f: not _matches_patterns(f, ignore_globs), filenames
            )

            # As we iterate from bottom to top, we can access the elements from
            # the lookup table as they are already created
            children: list[FileSystemItem] = [
                lookup[os.path.join(dirpath, sub_dir)]
                for sub_dir in os_sorted(_dirnames)
            ]

            # Add all files to children
            for filename in os_sorted(_filenames):
                full_path = os.path.join(dirpath, filename)
                # Here, we know this not a folder, so we can use fs_item_from_path.
                children.append(
                    fs_item_from_path(path=os.path.abspath(full_path), cache=cache)
                )

            # Add current directory to lookup
            lookup[dirpath] = Folder(
                children=children,
                full_path=os.path.abspath(dirpath),
                hash=dirhash_c(
                    dirpath,
                    cache,
                    filter_regex=audio_regex,  # Only hash audio files
                ).hex(),
                is_album=Path(dirpath) in album_folders,
            )

        return lookup[str(path)]

    def walk(self) -> Iterator[FileSystemItem]:
        """Walk the folder and yield all files and folders."""
        yield self
        for child in self.children:
            if isinstance(child, Folder):
                yield from child.walk()
            else:
                yield child


@dataclass
class Archive(FileSystemItem):
    # Defaults to true, as we assume that we can import an archive as an album
    is_album: bool = True

    def __init__(self, full_path: str, hash: str):
        super().__init__(
            full_path=full_path,
            hash=hash,
            is_album=True,  # Archives are always considered albums
            type="archive",
        )

    @classmethod
    def from_path(
        cls, path: Path | str, cache: Cache[str, bytes] | None = None
    ) -> Archive:
        """Create an Archive object from a path."""
        if isinstance(path, str):
            path = Path(path)

        if not is_archive_file(path):
            raise FileNotFoundError(f"Path `{path}` is not an archive file.")

        if cache is None:
            cache = Cache(maxsize=2**16)

        return cls(
            full_path=str(path.resolve()),
            hash=archive_hash(path, cache=cache).hex(),
        )


@cache
def allowed_archive_extensions() -> list[str]:
    # Tar files
    ext = [".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"]
    # Zip files
    ext += [".zip"]
    if importlib.util.find_spec("rarfile") is not None:
        ext += [".rar"]
    if importlib.util.find_spec("py7zr") is not None:
        ext += [".7z"]
    return ext


def is_archive_file(path: Path | str) -> bool:
    """Check if a file is an archive file based on its extension.

    It seems like there is a memory issue with `tarfile.is_tarfile`
    (see https://github.com/metasauce/beets-flask/issues/258). We try
    to avoid this by only checking the file extension here, and not trying to open the file.
    """
    allowed_extensions = allowed_archive_extensions()
    return Path(path).suffix.lower() in allowed_extensions


@dataclass
class File(FileSystemItem):
    def __init__(self, full_path: str):
        super().__init__(
            full_path=full_path,
            hash="",  # Files do not have a hash atm (maybe later we can add a hash)
            is_album=False,  # Files are not considered albums
            type="file",
        )

    @classmethod
    def from_path(
        cls, path: Path | str, cache: Cache[str, bytes] | None = None
    ) -> File:
        """Create a File object from a path."""
        if isinstance(path, str):
            path = Path(path)

        if not path.is_file():
            raise FileNotFoundError(f"Path `{path}` is not a file.")

        full_path = str(path.resolve())

        return cls(
            full_path=full_path,
        )


@cached(cache=TTLCache(maxsize=1024, ttl=900), info=True)
def path_to_folder(root_dir: Path | str, subdirs=True) -> Folder:
    """Generate our nested dict structure for the specified path.

    Parameters
    ----------
    root_dir : str
        The root directory to start from.
    subdirs : bool, optional
        Whether to mark qualifying subfolders of an album as album folders themselves. If true, e.g. for `/album/CD1/track.mp3` both `/album/` and `/album/CD1/` are flagged. Defaults to True.

    Returns
    -------
        dict: The nested dict structure.
    """

    return Folder.from_path(root_dir, subdirs=subdirs)


def album_folders_from_track_paths(
    track_paths: list[Path] | list[str], use_parent_for_multidisc: bool = True
) -> list[Path]:
    """Get all album folders from a list of paths to files.

    Parameters
    ----------
    track_paths : list[Path]
        list of track paths, e.g. mp3 files.
    use_parent_for_multidisc : bool, optional
        When files are in an album folder that might be a multi-disc folder (e.g. `/album/cd1`),
        return the parent (`/album`) instead of the lowest-level-folder (`/cd1`). Defaults to True.

    Returns
    -------
        list[str]: album folders
    """

    folders_to_check: set[Path] = set()
    album_folders: set[Path] = set()
    for path in track_paths:
        # FIXME: For backwards compatibility, we allow a string as input
        if isinstance(path, str):
            path = Path(path)

        if is_archive_file(path):
            album_folders.add(path.resolve())
        elif path.is_file():
            folders_to_check.add(path.parent.resolve())
        else:
            # just to be nice and manage directories instead of files
            folders_to_check.add(path.resolve())

    for folder in folders_to_check:
        afs = all_album_folders(folder, subdirs=True)
        for af in afs:
            album_folders.add(af)

    if use_parent_for_multidisc:
        parents: set[Path] = set()
        children: set[Path] = set()
        for folder in album_folders:
            if _is_within_multi_dir(folder):
                parents.add(folder.parent)
                children.add(folder)

        album_folders = album_folders - children
        album_folders = album_folders.union(parents)

    return sorted(album_folders, key=lambda s: str(s).lower())


def is_album_folder(path: Path | str):
    """Check if a path is an album folder.

    Returns true if the path is detected as an album by beets, or if it is an archive file.
    -------
    path : Path | str
        The path to check, can be a folder, file or archive.

    Note
    ----
    Except in tests, we dont use this function yet.
    Its logic is duplicated in `all_album_folders`. (We should consolidate.)
    """
    if isinstance(path, str):
        path = Path(path).absolute()
    if is_archive_file(path):
        return True
    for paths, items in albums_in_dir(bytestring_path(path)):
        items_str = [i.decode("utf-8") for i in items]
        if all(is_archive_file(i) for i in items_str):
            continue
        # Same music-file requirement as in `all_album_folders`.
        if not any(audio_regex.match(os.path.basename(i)) for i in items_str):
            continue
        if str(path).encode("utf-8") in paths:
            return True
    return False


def all_album_folders(root_dir: Path | str, subdirs: bool = False) -> list[Path]:
    """
    Get all album folders from a given root dir.

    Parameters
    ----------
    root_dir : str
        toppath, highest level to start searching.
    subdirs : bool, optional
        Whether to return subfolders of an album that themselves would qualify.
        E.g. a `CD1` folder. Defaults to False.

    Returns
    -------
        list[Path]
    """

    if isinstance(root_dir, str):
        root_dir = Path(root_dir)

    folders: list[bytes] = []
    for paths, items in albums_in_dir(bytestring_path(root_dir.absolute())):
        items_str = [i.decode("utf-8") for i in items]

        # Our choice on handling archives:
        # - archives are always simple albums. no multi-disc logic supported,
        #   all discs need to be _inside_ the archive.
        # - if a folder contains only archives, it will never be considered an
        #   album folder
        # - if a folder contains a mix of archives and music files, it will be
        #   considered an album folder (as we think archives might be metadata or additional files e.g. cover art)
        if all(is_archive_file(i) for i in items_str):
            folders.extend(items)
            continue

        # beets `albums_in_dir` treats any directory with *any* files as an
        # album. Require at least one music file; stray uploads or cover art
        # without music do not make a folder an album.
        if not any(audio_regex.match(os.path.basename(i)) for i in items_str):
            continue

        if subdirs:
            folders.extend(p for p in paths)
        else:
            # the top-level path is always the first in the list
            # however, there is an edgecase, if we have a rogue element in a multi-disc folder:
            # - artist/album/should_not_be_here.mp3
            # - artist/album/CD1/track.mp3
            # - artist/album/CD2/track.mp3
            # -> then albums_in_dir returns [album], [CD1, CD2] so that picking the first element is wrong.
            # we would want all 3: album, CD1 and CD2. but in this case, the parent `album` should already
            # be in our set when we check [CD1, CD2]
            if os.path.dirname(paths[0]) in folders:
                folders.extend(p for p in paths)
            else:
                folders.append(paths[0])

    return [Path(f.decode("utf-8")) for f in folders]


def _is_within_multi_dir(path: Path | str) -> bool:
    """
    Minimal version of beets heuristic to check if a string matches a multi-disc pattern.

    E.g. "My Album CD1" or "Disc 2" will return True
    """

    if isinstance(path, str):
        path = Path(path)

    path_str = path.name  # Use pathlib to get the basename

    for marker_pat in MULTIDISC_PATTERNS:
        match = marker_pat.match(path_str.encode("utf-8"))
        if match:
            return True
    return False


@cached(cache=TTLCache(maxsize=1024, ttl=60), info=True)
def dir_size(path: Path) -> int:
    """Size of a dir in bytes, including content."""
    try:
        result = subprocess.run(
            ["du", "-sb", str(path.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        size = int(result.stdout.split()[0])
        return size
    except Exception as e:
        # this happens e.g. if the directory does not exist.
        log.error(e)
        return -1


@cached(cache=TTLCache(maxsize=1024, ttl=60), info=True)
def dir_files(path: Path) -> int:
    """Count the number of files in a directory."""
    try:
        result = subprocess.run(
            [f"find {str(path.resolve())} | wc -l"],
            capture_output=True,
            text=True,
            check=True,
            shell=True,
        )
        count = int(result.stdout)
        return count
    except Exception as e:
        # this happens e.g. if the directory does not exist.
        log.error(e)
        return -1


def clear_cache():
    """Clear the cache for all cached functions."""
    path_to_folder.cache.clear()  # type: ignore
    dir_size.cache.clear()  # type: ignore
    dir_files.cache.clear()  # type: ignore


__all__ = ["dir_size", "fs_item_from_path"]
