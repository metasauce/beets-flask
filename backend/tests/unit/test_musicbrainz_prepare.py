from unittest import mock

from beets.library import Album

from beets_flask.server.routes.musicbrainz.prepare import prepare_release
from tests.conftest import beets_lib_album, beets_lib_item

EDITOR_URL = "https://musicbrainz.org/release/add"
MBID_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestPrepareRelease:
    def test_full_album(self):
        """A fully tagged album should produce complete output without flags."""
        item = beets_lib_item(
            title="Track 1",
            artist="The Artist",
            track=1,
            disc=1,
            isrc="QZ5AB1840341",
            mb_trackid="mb-track-1",
            length=231.0,
            media="Digital Media",
        )
        album = beets_lib_album(
            album="The Album",
            albumartist="The Artist",
            year=2017,
            label="Some Label",
            barcode="0723540055629",
            catalognum="CAT-001",
            country="BR",
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["album_id"] == 0  # not stored in a library yet
        assert prepared["editor_url"] == EDITOR_URL
        assert prepared["release"]["album"] == "The Album"
        assert prepared["release"]["albumartist"] == "The Artist"
        assert prepared["release"]["year"] == 2017
        assert prepared["release"]["label"] == "Some Label"
        assert prepared["release"]["barcode"] == "0723540055629"
        assert prepared["release"]["catalognum"] == "CAT-001"
        assert prepared["release"]["media"] == "Digital Media"

        assert len(prepared["tracks"]) == 1
        track = prepared["tracks"][0]
        assert track["title"] == "Track 1"
        assert track["isrc"] == "QZ5AB1840341"
        assert track["mb_trackid"] == "mb-track-1"
        assert track["length"] == 231.0

        assert prepared["flags"]["on_musicbrainz"] is False
        assert prepared["flags"]["missing"] == []
        assert prepared["flags"]["missing_isrc"] == []
        assert prepared["flags"]["multi_disc"] is False

        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert all(
            c["filled"] for c in checklist.values() if c["key"] != "on_musicbrainz"
        )
        assert checklist["on_musicbrainz"]["filled"] is False
        assert checklist["on_musicbrainz"]["note"] is not None

    def test_missing_fields(self):
        """Albums without label/barcode/catalog/country are flagged."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="Digital Media"
        )
        album = beets_lib_album(album="The Album", albumartist="Artist")
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert set(prepared["flags"]["missing"]) == {
            "label",
            "barcode",
            "catalognum",
            "country",
        }
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert checklist["label"]["filled"] is False
        assert checklist["barcode"]["filled"] is False

    def test_tracks_sorted_by_disc_and_track(self):
        """Tracks should be sorted by disc and then track number."""
        items = [
            beets_lib_item(title="D1T2", artist="Artist", disc=1, track=2),
            beets_lib_item(title="D2T1", artist="Artist", disc=2, track=1),
            beets_lib_item(title="D1T1", artist="Artist", disc=1, track=1),
        ]
        album = beets_lib_album(album="The Album", albumartist="Artist", disctotal=2)
        with mock.patch.object(Album, "items", return_value=items):
            prepared = prepare_release(album, EDITOR_URL)

        assert [t["title"] for t in prepared["tracks"]] == [
            "D1T1",
            "D1T2",
            "D2T1",
        ]
        assert prepared["flags"]["multi_disc"] is True

    def test_missing_isrc_flagged_per_track(self):
        """Tracks without ISRC should be listed in missing_isrc."""
        items = [
            beets_lib_item(
                title="With ISRC", artist="Artist", track=1, isrc="QZ5AB1840341"
            ),
            beets_lib_item(title="No ISRC", artist="Artist", track=2),
        ]
        album = beets_lib_album(album="The Album", albumartist="Artist")
        with mock.patch.object(Album, "items", return_value=items):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["flags"]["missing_isrc"] == ["No ISRC"]
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert checklist["isrc"]["filled"] is False

    def test_multi_artist(self):
        """Albums with multiple track artists should be flagged."""
        items = [
            beets_lib_item(title="A", artist="Artist A", track=1),
            beets_lib_item(title="B", artist="Artist B", track=2),
        ]
        album = beets_lib_album(album="The Album", albumartist="Artist A")
        with mock.patch.object(Album, "items", return_value=items):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["flags"]["multi_artist"] is True

    def test_on_musicbrainz(self):
        """Albums with an mb_albumid should be flagged as on musicbrainz."""
        item = beets_lib_item(title="Track 1", artist="Artist", track=1)
        album = beets_lib_album(
            album="The Album",
            albumartist="Artist",
            mb_albumid="12345678-9abc-def0-1234-56789abcdef0",
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["flags"]["on_musicbrainz"] is True
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert "note" not in checklist["on_musicbrainz"]


    def test_media_adjusted_to_vinyl_for_pre_cd_album(self):
        """A CD rip of an album older than the CD gets Vinyl in its place."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="CD"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1970, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["release"]["media"] == "Vinyl"
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert checklist["format"]["filled"] is True
        assert "CD adjusted to Vinyl" in checklist["format"]["note"]

    def test_media_kept_when_format_exists_at_year(self):
        """A format that already existed at the release year is kept."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="CD"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1990, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["release"]["media"] == "CD"
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert "note" not in checklist["format"]

    def test_media_original_exposes_library_tag(self):
        """The library media is kept so the UI can offer it as an option."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="CD"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1970, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["release"]["media"] == "Vinyl"
        assert prepared["release"]["media_original"] == "CD"
        assert "CD" in prepared["media_formats"]
        assert "Vinyl" in prepared["media_formats"]
        assert prepared["default_media_format"] == "CD"

    def test_media_original_absent_when_not_adjusted(self):
        """No media_original when the library format is already valid."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="CD"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1990, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert "media_original" not in prepared["release"]


class TestBuildEditorFields:
    def _fields(self, prepared) -> dict[str, str]:
        return {f["name"]: f["value"] for f in prepared["release_editor_fields"]}

    def test_full_album(self):
        """All known values should map to release editor form fields."""
        item = beets_lib_item(
            title="Track 1",
            artist="The Artist",
            track=1,
            disc=1,
            length=231.0,
            media="Digital Media",
        )
        album = beets_lib_album(
            album="The Album",
            albumartist="The Artist",
            year=2017,
            month=4,
            day=5,
            label="Some Label",
            barcode="0723540055629",
            catalognum="CAT-001",
            country="br",
            albumtype="album",
            albumstatus="official",
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["name"] == "The Album"
        assert fields["barcode"] == "0723540055629"
        assert fields["date.year"] == "2017"
        assert fields["date.month"] == "4"
        assert fields["date.day"] == "5"
        assert fields["country"] == "BR"
        assert fields["status"] == "Official"
        assert fields["type"] == "Album"
        assert fields["artist_credit.names.0.name"] == "The Artist"
        assert fields["labels.0.name"] == "Some Label"
        assert fields["labels.0.catalog_number"] == "CAT-001"
        assert fields["mediums.0.format"] == "Digital Media"
        assert fields["mediums.0.track.0.name"] == "Track 1"
        assert fields["mediums.0.track.0.number"] == "1"
        assert fields["mediums.0.track.0.length"] == "231000"
        assert "mediums.0.track.0.artist_credit.names.0.name" not in fields

    def test_unknown_type_and_status_are_skipped(self):
        """Values not recognized by MusicBrainz must not be sent."""
        item = beets_lib_item(title="Track 1", artist="Artist", track=1)
        album = beets_lib_album(
            album="The Album",
            albumartist="Artist",
            year=2020,
            albumtype="not-a-real-type",
            albumstatus="weird",
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert "type" not in fields
        assert "status" not in fields

    def test_malformed_language_script_and_country_are_skipped(self):
        """Non-ISO values must not be sent, they would fail the seed."""
        item = beets_lib_item(title="Track 1", artist="Artist", track=1)
        album = beets_lib_album(
            album="The Album",
            albumartist="Artist",
            year=2020,
            country="Brazil",
            language="English",
            script="Latin",
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert "country" not in fields
        assert "language" not in fields
        assert "script" not in fields

    def test_valid_language_script_and_country_are_sent(self):
        """ISO codes in the expected format should be sent."""
        item = beets_lib_item(title="Track 1", artist="Artist", track=1)
        album = beets_lib_album(
            album="The Album",
            albumartist="Artist",
            year=2020,
            country="us",
            language="eng",
            script="latn",
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["country"] == "US"
        assert fields["language"] == "eng"
        assert fields["script"] == "latn"

    def test_multi_disc_grouped_into_mediums(self):
        """One medium per disc, with the format and track numbers."""
        items = [
            beets_lib_item(title="D1T1", artist="Artist", disc=1, track=1, length=10.5),
            beets_lib_item(title="D1T2", artist="Artist", disc=1, track=2, length=20.5),
            beets_lib_item(title="D2T1", artist="Artist", disc=2, track=1, length=30.5),
        ]
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=2000, disctotal=2
        )
        with mock.patch.object(Album, "items", return_value=items):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.name"] == "Disc 1"
        assert fields["mediums.1.name"] == "Disc 2"
        assert fields["mediums.0.track.0.name"] == "D1T1"
        assert fields["mediums.0.track.1.name"] == "D1T2"
        assert fields["mediums.1.track.0.name"] == "D2T1"
        assert fields["mediums.1.track.0.length"] == "30500"

    def test_track_artist_credit_only_when_different(self):
        """Track artists that differ from the album artist get an artist credit."""
        items = [
            beets_lib_item(title="Feat", artist="Main, Feat", track=1, length=60.0),
            beets_lib_item(title="Solo", artist="Main", track=2, length=60.0),
        ]
        album = beets_lib_album(
            album="The Album", albumartist="Main", year=2020, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=items):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.track.0.artist_credit.names.0.name"] == "Main, Feat"
        assert (
            fields["mediums.0.track.0.artist_credit.names.0.artist.name"]
            == "Main, Feat"
        )
        assert "mediums.0.track.0.artist_credit.names.0.mbid" not in fields
        assert "mediums.0.track.1.artist_credit.names.0.name" not in fields

    def test_unknown_media_defaults_to_cd(self):
        """Media names MusicBrainz does not know must default to CD."""
        item = beets_lib_item(title="Track 1", artist="Artist", track=1, media="LP")
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=2020, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.format"] == "CD"

    def test_known_media_is_kept(self):
        """Media names MusicBrainz knows must be sent as-is."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media='7" Vinyl'
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=2020, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.format"] == '7" Vinyl'

    def test_pre_cd_album_seeds_vinyl_instead_of_cd(self):
        """CD must not be seeded for an album older than the CD format."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="CD"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1970, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.format"] == "Vinyl"

    def test_anachronistic_digital_format_seeds_cd(self):
        """A format that postdates the album falls back to CD (from 1982)."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="MiniDisc"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1990, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.format"] == "CD"

    def test_unknown_media_defaults_to_vinyl_for_pre_cd_album(self):
        """Unknown media on an old album must not default to CD."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="LP"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=1970, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.format"] == "Vinyl"

    def test_media_kept_when_no_year(self):
        """Without a year there is no way to detect an anachronistic format."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="CD"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=0, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["mediums.0.format"] == "CD"

    def test_artist_mbid_seeded_when_known(self):
        """A stored artist MBID must be seeded so the editor resolves it."""
        item = beets_lib_item(title="Track 1", artist="The Artist", track=1)
        album = beets_lib_album(
            album="The Album",
            albumartist="The Artist",
            year=2020,
            disctotal=1,
            mb_albumartistid="abc-123",
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["artist_credit.names.0.name"] == "The Artist"
        assert fields["artist_credit.names.0.artist.name"] == "The Artist"
        assert fields["artist_credit.names.0.mbid"] == "abc-123"

    def test_artist_mbid_skipped_when_missing(self):
        """Without a stored artist MBID no mbid field must be sent."""
        item = beets_lib_item(title="Track 1", artist="The Artist", track=1)
        album = beets_lib_album(
            album="The Album", albumartist="The Artist", year=2020, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["artist_credit.names.0.name"] == "The Artist"
        assert fields["artist_credit.names.0.artist.name"] == "The Artist"
        assert "artist_credit.names.0.mbid" not in fields

    def test_track_artist_mbid_seeded(self):
        """Track artist credits get the stored track artist MBID."""
        item = beets_lib_item(
            title="Feat",
            artist="The Featuring Artist",
            track=1,
            mb_artistid="track-artist-9",
        )
        album = beets_lib_album(
            album="The Album", albumartist="Main", year=2020, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert (
            fields["mediums.0.track.0.artist_credit.names.0.name"]
            == "The Featuring Artist"
        )
        assert (
            fields["mediums.0.track.0.artist_credit.names.0.artist.name"]
            == "The Featuring Artist"
        )
        assert (
            fields["mediums.0.track.0.artist_credit.names.0.mbid"] == "track-artist-9"
        )

    def test_only_available_fields_are_sent(self):
        """Missing values must not produce any editor field."""
        item = beets_lib_item(
            title="Untitled", artist="the album artist", track=1, disc=1
        )
        album = beets_lib_album(
            album="The Album", albumartist="the album artist", year=0, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        fields = self._fields(prepared)
        assert fields["name"] == "The Album"
        assert "barcode" not in fields
        assert "date.year" not in fields
        assert "labels.0.name" not in fields
        assert "labels.0.catalog_number" not in fields
        assert "country" not in fields
        assert fields["mediums.0.format"] == "CD"
        assert fields["mediums.0.track.0.name"] == "Untitled"
        assert "mediums.0.track.0.length" not in fields


class TestBuildArtists:
    def _album(self, **kwargs):
        item = beets_lib_item(title="Track 1", artist="Main Artist", track=1)
        album = beets_lib_album(
            album="The Album", albumartist="Main Artist", year=2020, disctotal=1
        )
        return item, album

    def _prepare(self, album, lookup=None):
        return prepare_release(album, EDITOR_URL, lookup=lookup)

    def test_unknown_when_no_lookup(self):
        """Without a lookup artists without MBID are marked unknown."""
        item, album = self._album()
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = self._prepare(album)

        artists = prepared["artists"]
        assert [a["name"] for a in artists] == ["Main Artist"]
        assert artists[0]["exists"] == "unknown"
        assert artists[0]["matches"] == []
        assert "create_url" in artists[0]
        assert artists[0]["mbid_fields"] == ["artist_credit.names.0.mbid"]

    def test_stored_mbid_stays_yes_and_fetches_matches(self):
        """A stored MBID keeps exists=yes, but matches are still fetched."""
        item, album = self._album()
        album["mb_albumartistid"] = MBID_A
        matches = [{"name": "Main Artist", "mbid": MBID_A, "score": 100}]
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = self._prepare(album, lookup=lambda name: matches)

        artist = prepared["artists"][0]
        assert artist["exists"] == "yes"
        assert artist["mbid"] == MBID_A
        assert artist["matches"] == matches
        assert artist["artist_url"] == f"https://musicbrainz.org/artist/{MBID_A}"
        assert "create_url" not in artist
        fields = {f["name"]: f["value"] for f in prepared["release_editor_fields"]}
        assert fields["artist_credit.names.0.mbid"] == MBID_A

    def test_no_match_is_missing(self):
        """An empty search result marks the artist as not on MusicBrainz."""
        item, album = self._album()
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = self._prepare(album, lookup=lambda name: [])

        artist = prepared["artists"][0]
        assert artist["exists"] == "no"
        assert "create_url" in artist
        assert artist["create_url"].startswith(
            "https://musicbrainz.org/artist/create?edit-artist.name=Main+Artist"
        )

    def test_exact_match_is_yes(self):
        """An exact name match marks the artist as existing and preselected."""
        item, album = self._album()
        matches = [
            {"name": "Main Artist", "mbid": MBID_A, "score": 100},
            {"name": "Main Artist (US)", "mbid": "x", "score": 40},
        ]
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = self._prepare(album, lookup=lambda name: matches)

        artist = prepared["artists"][0]
        assert artist["exists"] == "yes"
        assert artist["matches"] == matches
        assert artist["mbid"] == MBID_A
        assert artist["artist_url"] == f"https://musicbrainz.org/artist/{MBID_A}"
        assert "create_url" not in artist

    def test_fuzzy_only_is_maybe(self):
        """Only fuzzy matches mark the artist as maybe."""
        item, album = self._album()
        matches = [{"name": "Main Artist (US)", "mbid": "x", "score": 55}]
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = self._prepare(album, lookup=lambda name: matches)

        artist = prepared["artists"][0]
        assert artist["exists"] == "maybe"
        assert "create_url" in artist

    def test_track_artists_and_mbid_fields(self):
        """Track artists get their own mbid field keys."""
        items = [
            beets_lib_item(title="A", artist="Main", track=1, mb_artistid=MBID_A),
            beets_lib_item(title="B", artist="Feat Guest", track=2),
        ]
        album = beets_lib_album(
            album="The Album",
            albumartist="Main",
            mb_albumartistid=MBID_A,
            year=2020,
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=items):
            prepared = self._prepare(album, lookup=lambda name: [])

        artists = {a["name"]: a for a in prepared["artists"]}
        assert prepared["artists"][0]["name"] == "Main"
        assert set(artists) == {"Main", "Feat Guest"}
        assert artists["Main"]["exists"] == "yes"
        assert artists["Main"]["mbid_fields"] == ["artist_credit.names.0.mbid"]
        assert artists["Feat Guest"]["exists"] == "no"
        assert artists["Feat Guest"]["mbid_fields"] == [
            "mediums.0.track.1.artist_credit.names.0.mbid"
        ]

    def test_create_url_has_sort_name_and_edit_note(self):
        """The create url prefills name, sort name and an edit note."""
        item = beets_lib_item(title="Track 1", artist="Anti-Herói", track=1)
        album = beets_lib_album(
            album="Olhos de Hokusai",
            albumartist="Anti-Herói",
            albumartist_sort="Herói, Anti",
            year=2020,
            disctotal=1,
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = self._prepare(album, lookup=lambda name: [])

        url = prepared["artists"][0]["create_url"]
        assert "edit-artist.name=Anti-Her%C3%B3i" in url
        assert "edit-artist.sort_name=Her%C3%B3i%2C+Anti" in url
        assert "Artist+created+via+beets-flask+from+the+album+%27Olhos+de+Hokusai%27" in url


class TestOnMusicbrainzAndMedia:
    def test_digital_media_inferred_from_format(self):
        """FLAC files without a media tag seed "Digital Media"."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="", format="FLAC"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=2017, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["release"]["media"] == "Digital Media"
        assert "media" not in prepared["flags"]["missing"]
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert checklist["format"]["filled"] is True

    def test_unknown_format_stays_missing_media(self):
        """A container that is not digital keeps media missing."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="", format=""
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", year=2017, disctotal=1
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert "media" in prepared["flags"]["missing"]
        assert "media" not in prepared["release"]

    def test_on_musicbrainz_from_lookup(self):
        """A barcode match marks the album as on MusicBrainz."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="Digital Media"
        )
        album = beets_lib_album(album="The Album", albumartist="Artist")
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(
                album, EDITOR_URL, on_musicbrainz=True
            )

        assert prepared["flags"]["on_musicbrainz"] is True
        checklist = {c["key"]: c for c in prepared["checklist"]}
        assert checklist["on_musicbrainz"]["filled"] is True
        assert "note" not in checklist["on_musicbrainz"]

    def test_missing_suppressed_when_on_musicbrainz(self):
        """Local field gaps are not flagged when the release already exists."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="Digital Media"
        )
        album = beets_lib_album(album="The Album", albumartist="Artist")
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(
                album, EDITOR_URL, on_musicbrainz=True
            )

        assert prepared["flags"]["missing"] == []

    def test_stored_mbid_wins_over_false_lookup(self):
        """A stored MBID keeps on_musicbrainz even if the lookup says no."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="Digital Media"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", mb_albumid=MBID_A
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(
                album, EDITOR_URL, on_musicbrainz=False
            )

        assert prepared["flags"]["on_musicbrainz"] is True


class TestCountries:
    def test_country_options_sorted_by_name(self):
        item = beets_lib_item(title="Track 1", artist="Artist", track=1)
        album = beets_lib_album(album="The Album", albumartist="Artist")
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        countries = prepared["countries"]
        assert len(countries) > 200
        assert countries[0]["name"] == "Afghanistan"
        assert {"code": "BR", "name": "Brazil"} in countries
        assert {"code": "US", "name": "United States"} in countries
        names = [c["name"] for c in countries]
        assert names == sorted(names)
        for c in countries:
            assert len(c["code"]) == 2
            assert c["code"].isupper()

    def test_seeded_country_matches_option_code(self):
        """A tagged country stays available and uppercase in the editor fields."""
        item = beets_lib_item(
            title="Track 1", artist="Artist", track=1, media="Digital Media"
        )
        album = beets_lib_album(
            album="The Album", albumartist="Artist", country="br"
        )
        with mock.patch.object(Album, "items", return_value=[item]):
            prepared = prepare_release(album, EDITOR_URL)

        assert prepared["release"]["country"] == "br"
        assert any(
            f["name"] == "country" and f["value"] == "BR"
            for f in prepared["release_editor_fields"]
        )
