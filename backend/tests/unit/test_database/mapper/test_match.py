from beets.autotag.distance import Distance as BeetsDistance
from beets.autotag.hooks import AlbumInfo as BeetsAlbumInfo
from beets.autotag.hooks import TrackInfo as BeetsTrackInfo
from beets.autotag.match import AlbumMatch as BeetsAlbumMatch
from beets.autotag.match import TrackMatch as BeetsTrackMatch

from beets_flask.database.mapper.base import Context
from beets_flask.database.mapper.match import (
    AlbumInfoMapper,
    AlbumMatchMapper,
    DistanceMapper,
    MatchMapper,
    TrackInfoMapper,
    TrackMatchMapper,
)
from beets_flask.database.models.match import TrackInfo
from beets_flask.importer.types import BeetsItem
from tests.conftest import beets_lib_item


class TestTrackInfoMapper:
    """Tests that we can probably serialize and deserialize
    beets TrackInfo objs.
    """

    def test_roundtrip_conversion(self):
        """Test that we can convert BeetsTrackInfo to TrackInfo and back."""
        from beets.autotag.hooks import TrackInfo as BeetsTrackInfo

        original = BeetsTrackInfo(
            title="Test Track",
            artist="Test Artist",
            album="Test Album",
            length=180.0,
            index=1,
        )

        mapper = TrackInfoMapper()
        ctx = Context()

        # Test from_beets
        model = mapper.to_db(original, ctx)
        assert isinstance(model, TrackInfo)
        assert model.data["title"] == "Test Track"
        assert model.data["artist"] == "Test Artist"
        assert model.data["album"] == "Test Album"
        assert model.data["length"] == 180.0
        assert model.data["index"] == 1

        # Test to_beets
        result = mapper.from_db(model, ctx)
        assert result.title == original.title
        assert result.artist == original.artist
        assert result.album == original.album
        assert result.length == original.length
        assert result.index == original.index
        assert result.genres == original.genres


class TestAlbumInfoMatcher:
    """Tests that we can probably serialize and deserialize
    beets AlbumInfo objs.
    """

    def test_roundtrip_conversion(self):
        """Test converting model AlbumInfo to BeetsAlbumInfo."""
        from beets.autotag.hooks import AlbumInfo as BeetsAlbumInfo
        from beets.autotag.hooks import TrackInfo as BeetsTrackInfo

        original = BeetsAlbumInfo(
            tracks=[
                BeetsTrackInfo(title="a"),
                BeetsTrackInfo(title="b"),
            ],
            year=1,
        )

        mapper = AlbumInfoMapper()
        ctx = Context()

        # Test from_beets
        model = mapper.to_db(original, ctx)
        assert model.data["year"] == 1
        assert len(model.tracks) == 2
        assert model.tracks[0].data["title"] == "a"
        assert model.tracks[1].data["title"] == "b"

        # Test to_beets
        result = mapper.from_db(model, ctx)
        assert result.year == original.year
        assert len(result.tracks) == len(original.tracks)
        assert result.tracks[0].title == original.tracks[0].title
        assert result.tracks[1].title == original.tracks[1].title


class TestDistanceMapper:
    """Tests that we can probably serialize and deserialize
    beets Distance objs.
    """

    def test_roundtrip_conversion(self):
        """Test converting model Distance to BeetsDistance."""

        from beets.autotag.distance import Distance as BeetsDistance

        original = BeetsDistance()
        original.add("artist", 0.1)
        original.add("album", 0.2)

        mapper = DistanceMapper()
        ctx = Context()

        # Test from_beets
        model = mapper.to_db(original, ctx)
        assert model.max_distance == original.max_distance
        assert model.raw_distance == original.raw_distance

        # Test to_beets
        result = mapper.from_db(model, ctx)
        assert result.distance == original.distance
        assert result.max_distance == original.max_distance
        assert result.raw_distance == original.raw_distance
        assert result._penalties == original._penalties


def create_beets_album_match(
    album_id="abc123",
    album_name="Test Album",
    album_artist="Test Artist",
    album_track_count=2,
    album_url="https://example.com/album",
    album_image_path="/path/to/image.jpg",
    album_disambig="",
    tracks=None,
    distance_penalties=None,
    track_distances=None,
    mapping=None,
    extra_items=None,
    extra_tracks=None,
):
    """Factory function to generate beets AlbumMatch objects for testing purposes.

    Args:
        album_id: The album ID (default: "abc123")
        album_name: The album name (default: "Test Album")
        album_artist: The album artist (default: "Test Artist")
        album_track_count: Number of tracks to generate (default: 2)
        album_url: Album URL (default: "https://example.com/album")
        album_image_path: Album cover path (default: "/path/to/image.jpg")
        album_disambig: Album disambiguation (default: "")
        tracks: Custom list of TrackInfo objects. If None, generates from album_track_count.
        distance_penalties: Dict of {key: value} penalties. Defaults to {"artist": 0.1, "album": 0.2}
        track_distances: Dict of {TrackInfo: Dict of {key: value}} for track-level penalties.
                          e.g., {track1: {"track_title": 0.05}, track2: {"track_title": 0.0}}
        mapping: Dict of {Item: TrackInfo} mappings. If None, generates from album_track_count.
        extra_items: List of extra Item objects. If None, generates from album_track_count.
        extra_tracks: List of extra TrackInfo objects. If None, generates from album_track_count.

    Returns:
        beets.autotag.hooks.AlbumMatch: A test AlbumMatch object
    """

    # Default distance penalties
    if distance_penalties is None:
        distance_penalties = {"artist": 0.1, "album": 0.2}

    # Generate tracks if not provided
    if tracks is None:
        tracks = []
        for i in range(album_track_count):
            track = BeetsTrackInfo(
                title=f"Test Track {i + 1}",
                artist=album_artist,
                length=180.0 + i * 20,
                index=i + 1,
            )
            tracks.append(track)

    # Create AlbumInfo with the tracks
    album_info = BeetsAlbumInfo(
        album=album_name,
        artist=album_artist,
        tracks=tracks,
        album_id=album_id,
        album_url=album_url,
        album_image_path=album_image_path,
        album_disambig=album_disambig,
    )

    # Create Distance with penalties
    distance = BeetsDistance()
    for key, value in distance_penalties.items():
        distance.add(key, value)

    # Add track-level distances
    if track_distances is not None:
        for track, penalties in track_distances.items():
            track_distance = BeetsDistance()
            for key, value in penalties.items():
                track_distance.add(key, value)
            distance.tracks[track] = track_distance

    # Generate mapping if not provided
    if mapping is None:
        mapping = {}
        for i in range(album_track_count):
            item = beets_lib_item(title=f"mapping-{i}")
            info = BeetsTrackInfo(title=f"mapping-{i}")
            mapping[item] = info

    # Generate extra_tracks if not provided
    if extra_tracks is None:
        extra_tracks = []
        for i in range(album_track_count):
            extra_tracks.append(BeetsTrackInfo(title=f"extra-{i}"))

    # Generate extra_items if not provided
    if extra_items is None:
        extra_items = []
        for i in range(album_track_count):
            extra_items.append(beets_lib_item(title=f"extra-item-{i}"))

    return BeetsAlbumMatch(
        distance=distance,
        info=album_info,
        mapping=mapping,
        extra_tracks=extra_tracks,
        extra_items=extra_items,
    )


class TestAlbumMatchMapper:
    def test_roundtrip_conversion(self):
        """Test converting model TrackMatch to BeetsTrackMatch."""

        beets_track1 = BeetsTrackInfo(title="Test Track 1")
        beets_track2 = BeetsTrackInfo(title="Test Track 2")

        # Create some extra items using the test fixture
        extra_item1 = beets_lib_item(title="extra-item-1")
        extra_item2 = beets_lib_item(title="extra-item-2")

        beets_album_match = create_beets_album_match(
            album_id="abc123",
            tracks=[beets_track1, beets_track2],
            distance_penalties={"artist": 0.1, "album": 0.2},
            track_distances={
                beets_track1: {"track_title": 0.05},
                beets_track2: {"track_title": 0.0},
            },
            # We reuse objs here. Is a bit unrealistic
            # but fully tests our capabilites
            extra_tracks=[beets_track1],
            extra_items=[extra_item1, extra_item2],
            mapping={extra_item1: beets_track1},
        )

        mapper = AlbumMatchMapper()
        ctx = Context()

        # Test from_beets conversion
        model = mapper.to_db(beets_album_match, ctx)
        assert model.info.data["album_id"] == "abc123"
        assert model.info.data["album"] == "Test Album"
        assert model.info.data["artist"] == "Test Artist"
        assert len(model.info.tracks) == 2
        assert model.info.tracks[0].data["title"] == "Test Track 1"
        assert model.info.tracks[1].data["title"] == "Test Track 2"
        assert model.distance.raw_distance == beets_album_match.distance.raw_distance
        penalty_keys = {p.key for p in model.distance.penalties}
        assert penalty_keys == {"artist", "album"}
        assert len(model.distance.track_distances) == 2
        assert (
            len(model.track_mappings) == 4  # 1 mapping + 1 extra_track + 2 extra_items
        )

        # Test to_beets conversion
        result = mapper.from_db(model, ctx)
        assert result.info.album_id == "abc123"
        assert result.info.album == "Test Album"
        assert result.info.artist == "Test Artist"
        assert len(result.info.tracks) == 2
        assert result.info.tracks[0].title == "Test Track 1"
        assert result.info.tracks[1].title == "Test Track 2"
        assert result.distance.raw_distance == beets_album_match.distance.raw_distance
        assert len(result.mapping) == 1
        # Check dedbped worked as expected
        assert result.extra_items[0] in result.mapping.keys()
        assert result.mapping[result.extra_items[0]].title == beets_track1.title
        assert len(result.extra_items) == 2
        assert len(result.extra_tracks) == 1


class TestTrackMatchMapper:
    def test_roundtrip_conversion(self):
        """Test converting model TrackMatch to BeetsTrackMatch."""

        track_distance = BeetsDistance()
        track_distance.add("artist", 0.1)
        track_distance.add("album", 0.2)
        beets_track1 = BeetsTrackInfo(
            title="Test Track 1",
            artist="Test Artist",
            length=180.0,
            index=1,
        )
        beets_item = BeetsItem(
            title="Test Item 1",
        )

        original = BeetsTrackMatch(
            distance=track_distance,
            info=beets_track1,
            item=beets_item,
        )

        mapper = TrackMatchMapper()
        ctx = Context()

        # Test from_beets
        model = mapper.to_db(original, ctx)
        assert isinstance(model.info, TrackInfo)
        assert model.info.data["title"] == "Test Track 1"
        assert model.info.data["artist"] == "Test Artist"
        assert model.info.data["length"] == 180.0
        assert model.distance.raw_distance == track_distance.raw_distance
        assert model.item.fixed_values["title"] == beets_item.title
        assert len(model.distance.penalties) == 2

        # Test to_beets
        result = mapper.from_db(model, ctx)
        assert isinstance(result, BeetsTrackMatch)
        assert result.info.title == beets_track1.title
        assert result.info.artist == beets_track1.artist
        assert result.info.length == beets_track1.length
        assert result.distance.raw_distance == original.distance.raw_distance
        assert result.item.title == beets_item.title

        # Verify penalties are preserved
        penalty_keys = {p.key for p in model.distance.penalties}
        assert penalty_keys == {"artist", "album"}

    def test_roundtrip_album_match(self):
        """Test roundtrip conversion for AlbumMatch."""
        beets_track1 = BeetsTrackInfo(title="Test Track 1")
        beets_album_match = create_beets_album_match(
            album_id="abc123",
            album_name="Test Album",
            tracks=[beets_track1],
            distance_penalties={"artist": 0.1},
        )

        mapper = MatchMapper()
        ctx = Context()

        model = mapper.to_db(beets_album_match, ctx)
        result = mapper.from_db(model, ctx)

        assert isinstance(result, BeetsAlbumMatch)
        assert result.info.album_id == "abc123"
        assert result.info.album == "Test Album"

    def test_roundtrip_track_match(self):
        """Test roundtrip conversion for TrackMatch."""
        from beets.autotag.distance import Distance as BeetsDistance

        track_distance = BeetsDistance()
        track_distance.add("artist", 0.1)
        beets_track = BeetsTrackInfo(title="Test Track")
        beets_item = BeetsItem(title="Test Item 1")
        beets_track_match = BeetsTrackMatch(
            distance=track_distance,
            info=beets_track,
            item=beets_item,
        )

        mapper = MatchMapper()
        ctx = Context()

        model = mapper.to_db(beets_track_match, ctx)
        result = mapper.from_db(model, ctx)

        assert isinstance(result, BeetsTrackMatch)
        assert result.info.title == "Test Track"
        assert result.distance.raw_distance == track_distance.raw_distance
        assert result.item.title == beets_item.title
