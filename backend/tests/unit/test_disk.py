import os
import shutil
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from cachetools import Cache
from confuse import AttrDict

from beets_flask.dirhash_custom import dirhash_c
from beets_flask.disk import Folder, _matches_patterns, audio_regex


def touch(path):
    with open(path, "w") as f:
        pass


@pytest.fixture(scope="session")
def base(tmpdir_factory):
    """
    Create a folder structure for testing purposes.
    """
    base = str(tmpdir_factory.mktemp("beets_flask_disk"))

    # music files and misc
    os.makedirs(os.path.join(base, "artist/album_good"))
    source = Path(__file__).parent.parent / "data" / "audio"
    dest = Path(base) / "artist" / "album_good"
    shutil.copytree(source, dest, dirs_exist_ok=True)

    # remove multi folder
    shutil.rmtree(
        dest / "multi",
    )

    # empty folder
    os.makedirs(os.path.join(base, "artist/album_empty"))

    # no music files, just junk.
    # this depends on the ignored filetypes in the beets config.
    # but with the default config, hidden files should be ignored:
    os.makedirs(os.path.join(base, "artist/album_junk"))
    touch(os.path.join(base, "artist/album_junk/.junk.jpg"))

    # nested folders
    os.makedirs(os.path.join(base, "artist/album_multi/1/CD1"))
    os.makedirs(os.path.join(base, "artist/album_multi/1/CD2"))
    touch(os.path.join(base, "artist/album_multi/1/CD1/track_1.mp3"))
    touch(os.path.join(base, "artist/album_multi/1/CD2/track_1.mp3"))

    os.makedirs(os.path.join(base, "artist/album_multi/2/CD1"))
    os.makedirs(os.path.join(base, "artist/album_multi/2/CD2"))
    touch(os.path.join(base, "artist/album_multi/2/CD1/track_1.mp3"))
    touch(os.path.join(base, "artist/album_multi/2/CD2/track_1.mp3"))
    # the annoying rogue element
    touch(os.path.join(base, "artist/album_multi/2/should_not_be_here.mp3"))

    yield base

    shutil.rmtree(base)


@pytest.fixture(scope="session")
def s_base(tmpdir_factory):
    """
    Create a folder structure for testing purposes.
    No real files, just dummys
    """

    base = str(tmpdir_factory.mktemp("beets_flask_structure"))

    # We want to test if is_album_folder works correctly with the different structures.

    # empty folder
    os.makedirs(os.path.join(base, "artist/album_empty"))

    # nested folders
    os.makedirs(os.path.join(base, "artist/album_multi/CD1"))
    os.makedirs(os.path.join(base, "artist/album_multi/CD2"))
    touch(os.path.join(base, "artist/album_multi/CD1/track_1.mp3"))
    touch(os.path.join(base, "artist/album_multi/CD2/track_1.mp3"))

    # no music files, just junk.
    # this depends on the ignored filetypes in the beets config.
    # but with the default config, hidden files should be ignored:
    os.makedirs(os.path.join(base, "artist/album_junk"))
    touch(os.path.join(base, "artist/album_junk/.junk.jpg"))
    # non-hidden junk must not make the folder an album either
    touch(os.path.join(base, "artist/album_junk/foo.txt"))

    # the annoying rogue element (same as nested folders, but with a rogue file)
    os.makedirs(os.path.join(base, "artist/album_rogue/CD1"))
    os.makedirs(os.path.join(base, "artist/album_rogue/CD2"))
    touch(os.path.join(base, "artist/album_rogue/CD1/track_1.mp3"))
    touch(os.path.join(base, "artist/album_rogue/CD2/track_1.mp3"))
    touch(os.path.join(base, "artist/album_rogue/should_not_be_here.mp3"))

    # Good
    os.makedirs(os.path.join(base, "artist/album_good"))
    touch(os.path.join(base, "artist/album_good/track_1.mp3"))
    touch(os.path.join(base, "artist/album_good/track_2.mp3"))

    # Archive, needs to be an actual zip file, just touching is not enough for the beets' internal archive detection
    os.makedirs(os.path.join(base, "artist/archive"))
    with zipfile.ZipFile(os.path.join(base, "artist/archive/foo.zip"), "w") as _zipf:
        pass

    # Dir with archive and music files
    os.makedirs(os.path.join(base, "artist/archive_and_music"))
    touch(os.path.join(base, "artist/archive_and_music/track_1.mp3"))
    with zipfile.ZipFile(
        os.path.join(base, "artist/archive_and_music/foo.zip"), "w"
    ) as _zipf:
        pass

    yield base

    shutil.rmtree(base)


from beets_flask.disk import is_album_folder


class TestIsAlbumFolder:
    @pytest.mark.parametrize(
        "type",
        [Path, str],
    )
    def test_folder_empty(self, type, s_base):
        p = type(s_base + "/artist/album_empty")
        assert not is_album_folder(p)

    @pytest.mark.parametrize(
        "type",
        [Path, str],
    )
    def test_folder_good(self, type, s_base):
        p = type(s_base + "/artist/album_good")
        assert is_album_folder(p)

    def test_folder_junk(self, s_base):
        p = s_base + "/artist/album_junk"
        assert not is_album_folder(p)

    def test_folder_multi(self, s_base):
        assert is_album_folder(s_base + "/artist/album_multi")
        assert is_album_folder(s_base + "/artist/album_multi/CD1")
        assert is_album_folder(s_base + "/artist/album_multi/CD2")

    def test_folder_rogue(self, s_base):
        assert is_album_folder(s_base + "/artist/album_rogue")
        assert is_album_folder(s_base + "/artist/album_rogue/CD1")
        assert is_album_folder(s_base + "/artist/album_rogue/CD2")

    def test_archive(self, s_base):
        assert is_album_folder(s_base + "/artist/archive") == False
        assert is_album_folder(s_base + "/artist/archive/foo.zip")

    @pytest.mark.skip("is_album_folder tricky logic for archive and music")
    # but this is desired behaviour. revisit when consolidating
    # `is_album_folder` and `all_album_folders`
    def test_archive_and_music(self, s_base):
        assert is_album_folder(s_base + "/artist/archive_and_music")
        assert is_album_folder(s_base + "/artist/archive_and_music/foo.zip") == False


class TestAllAlbumFolders:
    @pytest.mark.parametrize(
        "type",
        [Path, str],
    )
    def test_no_subdirs(self, type, s_base):
        from beets_flask.disk import all_album_folders

        all_albums = [
            type(s_base + "/artist/album_good"),
            type(s_base + "/artist/album_multi"),
            # Rogue is detected as an album folder because of rogue file
            type(s_base + "/artist/album_rogue"),
            type(s_base + "/artist/album_rogue/CD1"),
            type(s_base + "/artist/album_rogue/CD2"),
            # Archive is detected as an album folder
            type(s_base + "/artist/archive/foo.zip"),
            # Archive and music is detected as an album folder
            # the archive inside is not
            type(s_base + "/artist/archive_and_music"),
        ]

        found_folders = all_album_folders(s_base)
        expected_folders = [Path(p) for p in all_albums]

        assert set(found_folders) == set(expected_folders)

    @pytest.mark.parametrize(
        "type",
        [Path, str],
    )
    def test_with_subdirs(self, type, s_base):
        from beets_flask.disk import all_album_folders

        all_albums_with_subdirs = [
            type(s_base + "/artist/album_good"),
            type(s_base + "/artist/album_multi"),
            type(s_base + "/artist/album_multi/CD1"),
            type(s_base + "/artist/album_multi/CD2"),
            type(s_base + "/artist/album_rogue"),
            type(s_base + "/artist/album_rogue/CD1"),
            type(s_base + "/artist/album_rogue/CD2"),
            # archives count as directories (album folders).
            type(s_base + "/artist/archive/foo.zip"),
            # Archive and music is detected as an album folder
            type(s_base + "/artist/archive_and_music"),
        ]

        found_folders = all_album_folders(s_base, subdirs=True)
        expected_folders = [Path(p) for p in all_albums_with_subdirs]

        assert set(found_folders) == set(expected_folders)

    # All zips in folder -> parent not album
    # One zip + other filers -> parent is album


class TestIsWithinMultiDir:
    @pytest.mark.parametrize(
        "type",
        [Path, str],
    )
    def test_is_within_multi_dir(self, type, s_base):
        from beets_flask.disk import _is_within_multi_dir

        assert _is_within_multi_dir(type(s_base + "/artist/album_multi/CD1"))
        assert _is_within_multi_dir(type(s_base + "/artist/album_multi/CD2"))
        # should work with and without trailing slashes
        assert _is_within_multi_dir(type(s_base + "/artist/album_rogue/CD1"))
        assert _is_within_multi_dir(type(s_base + "/artist/album_rogue/CD2"))
        assert not _is_within_multi_dir(type(s_base + "/artist/album_multi/"))
        assert not _is_within_multi_dir(type(s_base + "/artist/album_good/"))
        assert not _is_within_multi_dir(type(s_base + "/artist/archive/foo.zip"))


# input, use_parent_for_multidisc, expected
testdata = [
    (
        ["/artist/album_multi/1/CD1/track_1.mp3"],
        True,
        ["/artist/album_multi/1"],
    ),
    (
        ["/artist/album_multi/1/CD1/track_1.mp3"],
        False,
        ["/artist/album_multi/1/CD1"],
    ),
    (
        [
            "/artist/album_multi/1/CD1/track_1.mp3",
            "/artist/album_multi/1/CD2/track_1.mp3",
        ],
        True,
        ["/artist/album_multi/1"],
    ),
    (
        [
            "/artist/album_multi/1/CD1/track_1.mp3",
            "/artist/album_multi/1/CD2/track_1.mp3",
        ],
        False,
        [
            "/artist/album_multi/1/CD1",
            "/artist/album_multi/1/CD2",
        ],
    ),
]


@pytest.mark.parametrize(
    "input, use_parent_for_multidisc, expected",
    testdata,
)
def test_album_folders_from_track(
    base, input: list[str], use_parent_for_multidisc: bool, expected: list[str]
):
    from beets_flask.disk import album_folders_from_track_paths

    # Try legacy using string paths
    # TODO: Remove once we have migrated to Path objects
    folders = album_folders_from_track_paths(
        [base + p for p in input],
        use_parent_for_multidisc=use_parent_for_multidisc,
    )

    assert len(folders) == len(expected)
    for i, e in enumerate(expected):
        assert folders[i] == Path(base + e)

    # Test same thing with Path objects
    folders = album_folders_from_track_paths(
        [Path(base + p) for p in input],
        use_parent_for_multidisc=use_parent_for_multidisc,
    )

    assert len(folders) == len(expected)
    for i, e in enumerate(expected):
        assert folders[i] == Path(base + e)


cache_options: list[Cache | None] = [None, Cache(maxsize=2**16)]


@pytest.mark.parametrize(
    "cache",
    cache_options,
)
def test_dirhash(tmpdir_factory: pytest.TempdirFactory, cache: Cache | None):
    base = Path(tmpdir_factory.mktemp("dirhash_sample"))

    # adding a file directly inside
    hash_0 = dirhash_c(base, cache)
    (base / "dummy.txt").touch()
    assert dirhash_c(base, cache) != hash_0

    # when focusing on audio files, adding a txt should not change hash
    assert dirhash_c(base, cache, filter_regex=audio_regex) == hash_0

    (base / "dummy.mp3").touch()
    assert dirhash_c(base, cache, filter_regex=audio_regex) != hash_0

    # deletion back to old hash
    os.remove(base / "dummy.txt")
    os.remove(base / "dummy.mp3")
    assert dirhash_c(base, cache) == hash_0

    # creating subdirectories or moving them should change the hash
    os.makedirs(base / "subdir")
    hash_1 = dirhash_c(base, cache)
    assert hash_1 != hash_0

    os.rename(base / "subdir", base / "subdir2")
    assert dirhash_c(base, cache) != hash_1


@pytest.fixture
def tmp_dir_with_ignored_items(tmpdir):
    """Fixture to create a temporary directory with ignored files and folders."""
    base = Path(tmpdir)

    # Create ignored files and folders
    ignored_files = [
        ".hidden_file.txt",
        "temp_file.tmp",
        "backup~",
    ]
    ignored_dirs = [
        ".hidden_dir",
        "temp_dir",
    ]

    for file in ignored_files:
        (base / file).touch()

    for dir_name in ignored_dirs:
        (base / dir_name).mkdir()

    # Create non-ignored files and folders
    (base / "visible_file.txt").touch()
    (base / "visible_dir").mkdir()

    return base


def test_matches_patterns():
    """Test that _matches_patterns correctly identifies ignored patterns."""
    patterns = ["*.tmp", ".*", "*~", "temp_*"]

    # Files that should be ignored
    assert _matches_patterns("temp_file.tmp", patterns)
    assert _matches_patterns(".hidden", patterns)
    assert _matches_patterns("backup~", patterns)
    assert _matches_patterns("temp_dir", patterns)

    # Files that should not be ignored
    assert not _matches_patterns("visible.txt", patterns)
    assert not _matches_patterns("normal_file", patterns)
    assert not _matches_patterns("music.mp3", patterns)


def test_from_path_ignores_files_and_folders(tmp_dir_with_ignored_items):
    """Test that Folder.from_path ignores files and folders based on patterns."""
    # Mock the config to return specific ignore patterns
    ignore_patterns = ["*.tmp", ".*", "*~", "temp_*"]

    # Patch the get_config function to return our test ignore patterns
    with mock.patch("beets_flask.disk.get_config") as mock_get_config:
        mock_get_config.return_value = AttrDict(
            {
                "ignore_globs": ignore_patterns,
            }
        )

        folder = Folder.from_path(tmp_dir_with_ignored_items, subdirs=False)

        # Check that ignored files are not present
        ignored_files = [".hidden_file.txt", "temp_file.tmp", "backup~"]
        for file in ignored_files:
            assert not any(os.path.basename(c.full_path) == file for c in folder.walk())

        # Check that ignored directories are not present
        ignored_dirs = [".hidden_dir", "temp_dir"]
        for dir_name in ignored_dirs:
            assert not any(
                os.path.basename(c.full_path) == dir_name for c in folder.walk()
            )

        # Check that non-ignored items are present
        assert any(
            os.path.basename(c.full_path) == "visible_file.txt" for c in folder.walk()
        )
        assert any(
            os.path.basename(c.full_path) == "visible_dir" for c in folder.walk()
        )


def test_from_path_ignores_nested_items(tmpdir):
    """Test that Folder.from_path ignores nested files and folders."""
    base = Path(tmpdir)

    # Create a nested structure with ignored items
    (base / "visible_dir").mkdir()
    (base / "visible_dir" / ".hidden_nested").mkdir()
    (base / "visible_dir" / ".hidden_nested" / "file.txt").touch()
    (base / "visible_dir" / "temp_file.tmp").touch()
    (base / "visible_dir" / "normal_file.txt").touch()

    # Mock the config to return specific ignore patterns
    ignore_patterns = ["*.tmp", ".*"]

    with mock.patch("beets_flask.disk.get_config") as mock_get_config:
        mock_get_config.return_value = AttrDict(
            {
                "ignore_globs": ignore_patterns,
            }
        )

        folder = Folder.from_path(base, subdirs=True)

        # Check that ignored nested items are not present
        assert not any(
            os.path.basename(c.full_path) == ".hidden_nested" for c in folder.walk()
        )
        assert not any(
            os.path.basename(c.full_path) == "temp_file.tmp" for c in folder.walk()
        )

        # Check that non-ignored nested items are present
        assert any(
            os.path.basename(c.full_path) == "normal_file.txt" for c in folder.walk()
        )
