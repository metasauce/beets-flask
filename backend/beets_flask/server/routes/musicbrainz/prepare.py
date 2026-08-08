"""Logic to prepare a beets album for the MusicBrainz release editor.

The MusicBrainz API can not create or edit releases, so this module builds a
structured representation of an album (release fields, tracks, flags and a
checklist) that helps filling the release editor at
`https://musicbrainz.org/release/add` manually.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal, NotRequired, TypedDict
from urllib.parse import urlparse

from beets.library import Album, Item

from .mb import ArtistMatch, search_artist

#: Album keys (and a human readable label) that map to the release editor.
RELEASE_FIELDS: dict[str, str] = {
    "year": "Release year",
    "label": "Label",
    "barcode": "Barcode",
    "catalognum": "Catalog number",
    "country": "Country",
    "disctotal": "Total discs",
    "albumtype": "Album type",
    "genre": "Genre",
    "albumdisambig": "Release disambiguation",
    "mb_albumid": "MusicBrainz album id",
    "mb_albumartistid": "MusicBrainz artist id",
}

#: Keys that are considered "missing" if not set on the album.
REQUIRED_FIELDS = ["label", "barcode", "catalognum", "country"]

#: Albumartist separators that hint at multiple artists.
ARTIST_SEPARATORS = [",", ";", "&"]

#: Beets ``albumtype`` values -> MusicBrainz release group primary types.
RELEASE_TYPES = {
    "album": "Album",
    "single": "Single",
    "ep": "EP",
    "compilation": "Compilation",
    "soundtrack": "Soundtrack",
    "spokenword": "Spokenword",
    "interview": "Interview",
    "audiobook": "Audiobook",
    "audiodrama": "Audio drama",
    "audio drama": "Audio drama",
    "live": "Live",
    "remix": "Remix",
    "djmix": "DJ-mix",
    "dj-mix": "DJ-mix",
    "mixtape/street": "Mixtape/Street",
    "demo": "Demo",
    "field recording": "Field recording",
}

#: Beets ``albumstatus`` values -> MusicBrainz release statuses.
RELEASE_STATUSES = {
    "official": "Official",
    "promotion": "Promotion",
    "bootleg": "Bootleg",
    "pseudo-release": "Pseudo-Release",
}

#: ISO 3166-1 alpha-2 country codes and their English names. The MusicBrainz
#: release editor expects an uppercase two-letter code in the country field,
#: which is why the codes are used as the seeded value.
COUNTRIES: dict[str, str] = {
    "AF": "Afghanistan",
    "AX": "Åland Islands",
    "AL": "Albania",
    "DZ": "Algeria",
    "AS": "American Samoa",
    "AD": "Andorra",
    "AO": "Angola",
    "AI": "Anguilla",
    "AQ": "Antarctica",
    "AG": "Antigua and Barbuda",
    "AR": "Argentina",
    "AM": "Armenia",
    "AW": "Aruba",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BS": "Bahamas",
    "BH": "Bahrain",
    "BD": "Bangladesh",
    "BB": "Barbados",
    "BY": "Belarus",
    "BE": "Belgium",
    "BZ": "Belize",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BT": "Bhutan",
    "BO": "Bolivia",
    "BQ": "Bonaire, Sint Eustatius and Saba",
    "BA": "Bosnia and Herzegovina",
    "BW": "Botswana",
    "BV": "Bouvet Island",
    "BR": "Brazil",
    "IO": "British Indian Ocean Territory",
    "BN": "Brunei Darussalam",
    "BG": "Bulgaria",
    "BF": "Burkina Faso",
    "BI": "Burundi",
    "CV": "Cabo Verde",
    "KH": "Cambodia",
    "CM": "Cameroon",
    "CA": "Canada",
    "KY": "Cayman Islands",
    "CF": "Central African Republic",
    "TD": "Chad",
    "CL": "Chile",
    "CN": "China",
    "CX": "Christmas Island",
    "CC": "Cocos (Keeling) Islands",
    "CO": "Colombia",
    "KM": "Comoros",
    "CG": "Congo",
    "CD": "Congo (Democratic Republic of the)",
    "CK": "Cook Islands",
    "CR": "Costa Rica",
    "CI": "Côte d'Ivoire",
    "HR": "Croatia",
    "CU": "Cuba",
    "CW": "Curaçao",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DK": "Denmark",
    "DJ": "Djibouti",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "EC": "Ecuador",
    "EG": "Egypt",
    "SV": "El Salvador",
    "GQ": "Equatorial Guinea",
    "ER": "Eritrea",
    "EE": "Estonia",
    "SZ": "Eswatini",
    "ET": "Ethiopia",
    "FK": "Falkland Islands (Malvinas)",
    "FO": "Faroe Islands",
    "FJ": "Fiji",
    "FI": "Finland",
    "FR": "France",
    "GF": "French Guiana",
    "PF": "French Polynesia",
    "TF": "French Southern Territories",
    "GA": "Gabon",
    "GM": "Gambia",
    "GE": "Georgia",
    "DE": "Germany",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GR": "Greece",
    "GL": "Greenland",
    "GD": "Grenada",
    "GP": "Guadeloupe",
    "GU": "Guam",
    "GT": "Guatemala",
    "GG": "Guernsey",
    "GN": "Guinea",
    "GW": "Guinea-Bissau",
    "GY": "Guyana",
    "HT": "Haiti",
    "HM": "Heard Island and McDonald Islands",
    "VA": "Holy See",
    "HN": "Honduras",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "IS": "Iceland",
    "IN": "India",
    "ID": "Indonesia",
    "IR": "Iran",
    "IQ": "Iraq",
    "IE": "Ireland",
    "IM": "Isle of Man",
    "IL": "Israel",
    "IT": "Italy",
    "JM": "Jamaica",
    "JP": "Japan",
    "JE": "Jersey",
    "JO": "Jordan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KI": "Kiribati",
    "KP": "Korea (Democratic People's Republic of)",
    "KR": "Korea (Republic of)",
    "KW": "Kuwait",
    "KG": "Kyrgyzstan",
    "LA": "Lao People's Democratic Republic",
    "LV": "Latvia",
    "LB": "Lebanon",
    "LS": "Lesotho",
    "LR": "Liberia",
    "LY": "Libya",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MO": "Macao",
    "MG": "Madagascar",
    "MW": "Malawi",
    "MY": "Malaysia",
    "MV": "Maldives",
    "ML": "Mali",
    "MT": "Malta",
    "MH": "Marshall Islands",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MU": "Mauritius",
    "YT": "Mayotte",
    "MX": "Mexico",
    "FM": "Micronesia",
    "MD": "Moldova",
    "MC": "Monaco",
    "MN": "Mongolia",
    "ME": "Montenegro",
    "MS": "Montserrat",
    "MA": "Morocco",
    "MZ": "Mozambique",
    "MM": "Myanmar",
    "NA": "Namibia",
    "NR": "Nauru",
    "NP": "Nepal",
    "NL": "Netherlands",
    "NC": "New Caledonia",
    "NZ": "New Zealand",
    "NI": "Nicaragua",
    "NE": "Niger",
    "NG": "Nigeria",
    "NU": "Niue",
    "NF": "Norfolk Island",
    "MK": "North Macedonia",
    "MP": "Northern Mariana Islands",
    "NO": "Norway",
    "OM": "Oman",
    "PK": "Pakistan",
    "PW": "Palau",
    "PS": "Palestine",
    "PA": "Panama",
    "PG": "Papua New Guinea",
    "PY": "Paraguay",
    "PE": "Peru",
    "PH": "Philippines",
    "PN": "Pitcairn",
    "PL": "Poland",
    "PT": "Portugal",
    "PR": "Puerto Rico",
    "QA": "Qatar",
    "RE": "Réunion",
    "RO": "Romania",
    "RU": "Russia",
    "RW": "Rwanda",
    "BL": "Saint Barthélemy",
    "SH": "Saint Helena, Ascension and Tristan da Cunha",
    "KN": "Saint Kitts and Nevis",
    "LC": "Saint Lucia",
    "MF": "Saint Martin (French part)",
    "PM": "Saint Pierre and Miquelon",
    "VC": "Saint Vincent and the Grenadines",
    "WS": "Samoa",
    "SM": "San Marino",
    "ST": "Sao Tome and Principe",
    "SA": "Saudi Arabia",
    "SN": "Senegal",
    "RS": "Serbia",
    "SC": "Seychelles",
    "SL": "Sierra Leone",
    "SG": "Singapore",
    "SX": "Sint Maarten (Dutch part)",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "SB": "Solomon Islands",
    "SO": "Somalia",
    "ZA": "South Africa",
    "GS": "South Georgia and the South Sandwich Islands",
    "SS": "South Sudan",
    "ES": "Spain",
    "LK": "Sri Lanka",
    "SD": "Sudan",
    "SR": "Suriname",
    "SJ": "Svalbard and Jan Mayen",
    "SE": "Sweden",
    "CH": "Switzerland",
    "SY": "Syrian Arab Republic",
    "TW": "Taiwan",
    "TJ": "Tajikistan",
    "TZ": "Tanzania",
    "TH": "Thailand",
    "TL": "Timor-Leste",
    "TG": "Togo",
    "TK": "Tokelau",
    "TO": "Tonga",
    "TT": "Trinidad and Tobago",
    "TN": "Tunisia",
    "TR": "Türkiye",
    "TM": "Turkmenistan",
    "TC": "Turks and Caicos Islands",
    "TV": "Tuvalu",
    "UG": "Uganda",
    "UA": "Ukraine",
    "AE": "United Arab Emirates",
    "GB": "United Kingdom",
    "US": "United States",
    "UM": "United States Minor Outlying Islands",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VU": "Vanuatu",
    "VE": "Venezuela",
    "VN": "Viet Nam",
    "VG": "Virgin Islands (British)",
    "VI": "Virgin Islands (U.S.)",
    "WF": "Wallis and Futuna",
    "EH": "Western Sahara",
    "YE": "Yemen",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

#: Audio container formats that indicate a digital-only release. Used to seed
#: "Digital Media" when the library does not tag the physical medium.
DIGITAL_FORMATS = {
    "FLAC",
    "ALAC",
    "MP3",
    "AAC",
    "M4A",
    "OGG",
    "OPUS",
    "WAV",
    "AIFF",
    "APE",
    "WV",
    "WMA",
}

#: Medium format names that MusicBrainz knows (used for the seeded medium).
MB_MEDIA_FORMATS = {
    '12" Vinyl',
    '7" Vinyl',
    '10" Vinyl',
    "8cm CD",
    "Blu-ray",
    "Cassette",
    "CD",
    "Digital Media",
    "DualDisc",
    "DVD",
    "HDCD",
    "MiniDisc",
    "SACD",
    "Vinyl",
}

#: Medium format used when the album has no media or an unknown one.
DEFAULT_MEDIA_FORMAT = "CD"

#: Earliest year each MusicBrainz medium format existed. Formats not listed
#: (or ``None``) are assumed valid for any release date. MusicBrainz rejects
#: formats that did not exist when the release came out, so anachronistic
#: formats have to be replaced before seeding the editor.
MEDIA_FORMAT_SINCE: dict[str, int | None] = {
    '12" Vinyl': 1948,
    '7" Vinyl': 1949,
    '10" Vinyl': 1948,
    "8cm CD": 1982,
    "Blu-ray": 2006,
    "Cassette": 1963,
    "CD": 1982,
    "Digital Media": None,
    "DualDisc": 2004,
    "DVD": 1996,
    "HDCD": 1995,
    "MiniDisc": 1992,
    "SACD": 1999,
    "Vinyl": 1948,
}


class PreparedTrack(TypedDict):
    disc: int
    track: int
    title: str
    artist: str
    length: float  # seconds
    isrc: NotRequired[str]
    mb_trackid: NotRequired[str]
    mb_artistid: NotRequired[str]


class ReleaseData(TypedDict):
    album: str
    albumartist: str
    media: NotRequired[str]
    #: Media format as tagged in the library, before the year-based
    #: adjustment. Present when the prepared format differs from it.
    media_original: NotRequired[str]
    year: NotRequired[int]
    label: NotRequired[str]
    barcode: NotRequired[str]
    catalognum: NotRequired[str]
    country: NotRequired[str]
    disctotal: NotRequired[int]
    albumtype: NotRequired[str]
    genre: NotRequired[str]
    albumdisambig: NotRequired[str]
    mb_albumid: NotRequired[str]
    mb_albumartistid: NotRequired[str]


class ReleaseFlags(TypedDict):
    #: Whether the album already exists on MusicBrainz (i.e. has a MBID).
    on_musicbrainz: bool
    multi_disc: bool
    multi_artist: bool
    #: Keys of release fields that are not set (e.g. "label", "barcode").
    missing: list[str]
    #: Titles of tracks without an ISRC.
    missing_isrc: list[str]
    #: Titles of tracks without a track artist.
    missing_track_artist: list[str]


class ChecklistItem(TypedDict):
    key: str
    label: str
    filled: bool
    note: NotRequired[str]


class EditorField(TypedDict):
    #: Expanded CGI key for the MusicBrainz release editor form
    #: (e.g. ``mediums[0][track][2][name]``).
    name: str
    value: str


class CountryOption(TypedDict):
    code: str
    name: str


class PreparedArtist(TypedDict):
    name: str
    sort_name: NotRequired[str]
    #: MBID known from the beets library (not the one chosen in the UI).
    mbid: NotRequired[str]
    #: Dotted form field keys in ``release_editor_fields`` that carry this
    #: artist's MBID (e.g. ``artist_credit.names.0.mbid``). Used by the UI to
    #: override the artist with a selected match before opening the editor.
    mbid_fields: list[str]
    #: Whether the artist is on MusicBrainz: "yes", "maybe" (only fuzzy
    #: matches), "no" (no matches) or "unknown" (lookup disabled/failed).
    exists: Literal["yes", "maybe", "no", "unknown"]
    #: Matches returned by the MusicBrainz artist search (may be empty).
    matches: list[ArtistMatch]
    #: Url of the MusicBrainz artist page when an MBID is known.
    artist_url: NotRequired[str]
    #: Url that prefills the artist creation form, when the artist is not known.
    create_url: NotRequired[str]


class PreparedRelease(TypedDict):
    album_id: int
    #: Url of the MusicBrainz release editor (e.g. https://musicbrainz.org/release/add).
    editor_url: str
    release: ReleaseData
    tracks: list[PreparedTrack]
    #: Artists that appear in the release (album artist first, then track artists).
    artists: list[PreparedArtist]
    flags: ReleaseFlags
    checklist: list[ChecklistItem]
    #: MusicBrainz medium formats the UI can offer for the format selector.
    media_formats: list[str]
    #: Format used when the album has no usable media tag.
    default_media_format: str
    #: ISO 3166-1 alpha-2 codes with their English names, for the country
    #: selector shown when the album has no country tag.
    countries: list[CountryOption]
    #: Form fields to POST to ``editor_url`` to prefill the release editor.
    release_editor_fields: list[EditorField]


def _clean(value) -> object | None:
    """Return None for empty values (None, empty string or 0)."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if isinstance(value, (int, float)) and value == 0:
        return None
    return value


def _media(album: Album) -> str | None:
    """Media format of the album, taken from the first item.

    Falls back to the audio container for digital files, which beets stores
    in ``format`` (e.g. FLAC) while leaving the ``media`` tag empty.
    """
    items = list(album.items())
    if len(items) == 0:
        return None
    media = _clean(items[0].media)
    if media is not None:
        return str(media)
    fmt = _clean(items[0].format)
    if fmt is not None and str(fmt).upper() in DIGITAL_FORMATS:
        return "Digital Media"
    return None


def _medium_format(album: Album, media: str) -> str:
    """Return a MusicBrainz medium format that is valid for the album's year.

    MusicBrainz refuses formats that did not exist at the release date (e.g. a
    CD for a 1970 album — CDs only appeared in 1982). When the album predates
    the format, fall back to the newest format that already existed back then
    (Vinyl before 1982, CD from 1982 on). Media the library reports that
    MusicBrainz does not know default to :data:`DEFAULT_MEDIA_FORMAT` first.
    """
    if media not in MB_MEDIA_FORMATS:
        media = DEFAULT_MEDIA_FORMAT
    year = album.year
    if not year:
        return media
    since = MEDIA_FORMAT_SINCE.get(media)
    if since is not None and year < since:
        return "Vinyl" if year < 1982 else "CD"
    return media


def _build_tracks(items: list[Item], fallback_artist: str) -> list[PreparedTrack]:
    tracks: list[PreparedTrack] = []
    for item in sorted(items, key=lambda i: (i.disc or 0, i.track or 0)):
        track: PreparedTrack = {
            "disc": int(item.disc or 1),
            "track": int(item.track or 0),
            "title": item.title or "",
            "artist": item.artist or fallback_artist or "",
            "length": float(item.length or 0.0),
        }
        if _clean(item.isrc) is not None:
            track["isrc"] = str(item.isrc)
        if _clean(item.mb_trackid) is not None:
            track["mb_trackid"] = str(item.mb_trackid)
        mb_artistid = _clean(item.mb_artistid)
        if mb_artistid is None and item.mb_artistids:
            mb_artistid = item.mb_artistids[0]
        if mb_artistid is not None:
            track["mb_artistid"] = str(mb_artistid)
        tracks.append(track)
    return tracks


def _build_release(album: Album) -> ReleaseData:
    release: ReleaseData = {
        "album": album.album or "",
        "albumartist": album.albumartist or "",
    }
    for key in RELEASE_FIELDS:
        value = _clean(album[key])
        if value is not None:
            release[key] = value  # type: ignore[literal-required]
    media = _media(album)
    if media is not None:
        prepared_media = _medium_format(album, media)
        if prepared_media != media:
            release["media_original"] = media
        release["media"] = prepared_media
    return release


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _origin(url: str) -> str:
    """Scheme + host of a url, used to link to MusicBrainz entity pages."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _artist_create_url(
    name: str,
    sort_name: str | None = None,
    album_title: str | None = None,
    origin: str = "https://musicbrainz.org",
) -> str:
    """Url that prefills the MusicBrainz artist creation form.

    The MusicBrainz artist editor has no POST seeding (unlike the release
    editor), but it accepts the fields as GET query parameters and merges them
    into the form. Only fields that are safe to seed are used.
    """
    import urllib.parse

    note = "Artist created via beets-flask"
    if album_title:
        note += f" from the album '{album_title}'."
    else:
        note += "."
    params = [
        ("edit-artist.name", name),
        ("edit-artist.edit_note", note),
    ]
    if sort_name:
        params.insert(1, ("edit-artist.sort_name", sort_name))
    return f"{origin}/artist/create?" + urllib.parse.urlencode(params)


def _classify(
    name: str, mbid: str | None, matches: list[ArtistMatch] | None
) -> tuple[Literal["yes", "maybe", "no", "unknown"], list[ArtistMatch]]:
    """Decide whether an artist exists on MusicBrainz.

    Returns (exists, matches). A known MBID is accepted as "yes" without
    looking at the search results; a stored MBID already implies existence.
    """
    if mbid:
        return "yes", []
    if matches is None:
        return "unknown", []
    if not matches:
        return "no", []
    exact = [m for m in matches if _normalize(m.get("name", "")) == _normalize(name)]
    return ("yes" if exact else "maybe"), matches


def build_artists(
    album: Album,
    tracks: list[PreparedTrack],
    lookup: Callable[[str], list[ArtistMatch] | None] | None = search_artist,
    origin: str = "https://musicbrainz.org",
) -> list[PreparedArtist]:
    """List the artists of a release, checking which ones exist on MusicBrainz.

    The album artist comes first, followed by the distinct track artists. The
    lookup is only used to search artists that are new; artists with a stored
    MBID are marked as existing without a lookup.
    """
    artists: list[PreparedArtist] = []
    seen: set[str] = set()

    def add(name: str, mbid: str | None, sort_name: str | None) -> None:
        name = name.strip()
        key = _normalize(name)
        if not name or key in seen:
            return
        seen.add(key)

        searched = lookup(name) if lookup is not None else None
        if mbid:
            # A stored MBID already proves the artist exists, but we still
            # fetch the matches so the user can swap to another artist.
            exists: Literal["yes", "maybe", "no", "unknown"] = "yes"
            matches = searched if searched is not None else []
        else:
            exists, matches = _classify(name, None, searched)
            if exists == "yes":
                # Preselect the exact name match so the UI can just open the
                # editor with a resolved artist.
                for match in matches:
                    if _normalize(match.get("name", "")) == _normalize(name):
                        mbid = match.get("mbid")
                        break

        artist: PreparedArtist = {
            "name": name,
            "mbid_fields": [],
            "exists": exists,
            "matches": matches,
        }
        if sort_name:
            artist["sort_name"] = sort_name
        if mbid:
            artist["mbid"] = mbid
        if exists in ("no", "maybe", "unknown"):
            artist["create_url"] = _artist_create_url(
                name, sort_name, album.album or None, origin
            )
        artists.append(artist)

    albumartist = (album.albumartist or "").strip()
    if albumartist:
        mb_albumartistid = _clean(album.mb_albumartistid)
        add(
            albumartist,
            str(mb_albumartistid) if mb_albumartistid is not None else None,
            album.albumartist_sort,
        )
    for track in tracks:
        artist_name = track.get("artist")
        if artist_name:
            add(artist_name, track.get("mb_artistid"), None)
    return artists


def _artist_mbid_field_keys(
    release: ReleaseData, tracks: list[PreparedTrack]
) -> dict[str, list[str]]:
    """Map each artist name to the editor fields that carry its MBID."""
    mapping: dict[str, list[str]] = {}
    albumartist = (release.get("albumartist") or "").strip()
    if albumartist:
        mapping.setdefault(albumartist, []).append("artist_credit.names.0.mbid")

    discs: dict[int, list[PreparedTrack]] = {}
    for track in tracks:
        discs.setdefault(track["disc"], []).append(track)
    for medium_index, disc in enumerate(sorted(discs)):
        for track_index, track in enumerate(discs[disc]):
            artist = (track.get("artist") or "").strip()
            if artist and artist != albumartist:
                mapping.setdefault(artist, []).append(
                    f"mediums.{medium_index}.track.{track_index}."
                    "artist_credit.names.0.mbid"
                )
    return mapping


def _build_flags(
    album: Album, tracks: list[PreparedTrack], on_musicbrainz: bool
) -> ReleaseFlags:
    items = list(album.items())

    missing: list[str] = []
    for key in REQUIRED_FIELDS:
        if _clean(album[key]) is None:
            missing.append(key)
    if _media(album) is None:
        missing.append("media")
    if on_musicbrainz:
        # The release already exists on MusicBrainz with this data; the local
        # gaps are not needed to create it.
        missing = []

    track_artists = {t["artist"] for t in tracks if t["artist"]}
    multi_artist = len(track_artists) > 1 or any(
        sep in (album.albumartist or "") for sep in ARTIST_SEPARATORS
    )

    return ReleaseFlags(
        on_musicbrainz=on_musicbrainz,
        multi_disc=int(album.disctotal or 0) > 1,
        multi_artist=multi_artist,
        missing=missing,
        missing_isrc=[t["title"] for t in tracks if "isrc" not in t],
        missing_track_artist=[t["title"] for t in tracks if not t["artist"]],
    )


def _build_checklist(
    album: Album,
    release: ReleaseData,
    tracks: list[PreparedTrack],
    flags: ReleaseFlags,
) -> list[ChecklistItem]:
    def item(
        key: str, label: str, filled: bool, note: str | None = None
    ) -> ChecklistItem:
        out: ChecklistItem = {"key": key, "label": label, "filled": filled}
        if note:
            out["note"] = note
        return out

    raw_media = _media(album)
    media = release.get("media")
    format_note: str | None = None
    if raw_media is None:
        format_note = "No media format found (e.g. Digital Media, CD)"
    elif media is not None and raw_media != media:
        format_note = (
            f"Library format {raw_media} adjusted to {media}"
            f" for the {release.get('year', '?')} release year."
        )

    return [
        item(
            "title",
            "Release title",
            bool(release.get("album")),
            "Missing release title" if not release.get("album") else None,
        ),
        item(
            "artist",
            "Release artist",
            bool(release.get("albumartist")),
            "Missing artist" if not release.get("albumartist") else None,
        ),
        item(
            "format",
            "Format (media)",
            "media" in release,
            format_note,
        ),
        item(
            "tracks",
            f"Tracks ({len(tracks)})",
            len(tracks) > 0,
            "No tracks found" if len(tracks) == 0 else None,
        ),
        item(
            "year",
            "Release year",
            "year" in release,
            "Missing year" if "year" not in release else None,
        ),
        item(
            "label",
            "Label",
            "label" in release,
            "Missing label" if "label" not in release else None,
        ),
        item(
            "catalog",
            "Catalog number",
            "catalognum" in release,
            "Missing catalog number" if "catalognum" not in release else None,
        ),
        item(
            "barcode",
            "Barcode",
            "barcode" in release,
            "Missing barcode" if "barcode" not in release else None,
        ),
        item(
            "country",
            "Country",
            "country" in release,
            "Missing country" if "country" not in release else None,
        ),
        item(
            "isrc",
            f"ISRC on all tracks ({len(tracks) - len(flags['missing_isrc'])}/{len(tracks)})",
            len(flags["missing_isrc"]) == 0,
            (
                "Missing ISRC on: " + ", ".join(flags["missing_isrc"])
                if flags["missing_isrc"]
                else None
            ),
        ),
        item(
            "on_musicbrainz",
            "Already on MusicBrainz",
            flags["on_musicbrainz"],
            (
                "Album is not on MusicBrainz yet, create it in the release editor."
                if not flags["on_musicbrainz"]
                else None
            ),
        ),
    ]


def build_editor_fields(
    album: Album, release: ReleaseData, tracks: list[PreparedTrack]
) -> list[EditorField]:
    """Map prepared data to MusicBrainz release editor form fields.

    The MusicBrainz ``/release/add`` endpoint seeds the release editor from
    POSTed form fields (see ``MusicBrainz::Server::Controller::ReleaseEditor``).
    The keys use the dotted convention of ``CGI::Expand`` (e.g.
    ``labels.0.name``, ``mediums.0.track.1.length``), which is what the
    release editor seeding expects (see the ``mbs-7447`` seed fixture).
    Values that are not in the format MusicBrainz accepts are skipped so the
    seed does not fail.
    """
    fields: list[EditorField] = []

    def add(name: str, value: object) -> None:
        value = _clean(value)
        if value is not None:
            fields.append(EditorField(name=name, value=str(value)))

    add("name", release.get("album"))
    add("comment", release.get("albumdisambig"))
    add("barcode", release.get("barcode"))
    if album.year:
        add("date.year", int(album.year))
        if album.month:
            add("date.month", int(album.month))
        if album.day:
            add("date.day", int(album.day))
    country = _clean(album.country)
    if country is not None:
        country = str(country).upper()
        if re.fullmatch(r"[A-Z]{2}", country):
            add("country", country)
    if _clean(album.albumstatus) is not None:
        add("status", RELEASE_STATUSES.get(str(album.albumstatus).lower()))
    if _clean(album.albumtype) is not None:
        add("type", RELEASE_TYPES.get(str(album.albumtype).lower()))
    language = _clean(album.language)
    if isinstance(language, str) and re.fullmatch(r"[a-z]{3}", language):
        add("language", language)
    script = _clean(album.script)
    if isinstance(script, str) and re.fullmatch(r"[a-z]{4}", script):
        add("script", script)

    add("artist_credit.names.0.name", release.get("albumartist"))
    add("artist_credit.names.0.artist.name", release.get("albumartist"))
    add("artist_credit.names.0.mbid", release.get("mb_albumartistid"))

    label = release.get("label")
    if label:
        add("labels.0.name", label)
    add("labels.0.catalog_number", release.get("catalognum"))

    artist_name = release.get("albumartist") or ""
    discs: dict[int, list[PreparedTrack]] = {}
    for track in tracks:
        discs.setdefault(track["disc"], []).append(track)

    for medium_index, disc in enumerate(sorted(discs)):
        prefix = f"mediums.{medium_index}"
        media = release.get("media")
        format_name = media if media in MB_MEDIA_FORMATS else DEFAULT_MEDIA_FORMAT
        add(f"{prefix}.format", format_name)
        if len(discs) > 1:
            add(f"{prefix}.name", f"Disc {disc}")
        for track_index, track in enumerate(discs[disc]):
            track_prefix = f"{prefix}.track.{track_index}"
            add(f"{track_prefix}.name", track["title"])
            add(f"{track_prefix}.number", track["track"])
            if track["length"]:
                add(f"{track_prefix}.length", int(track["length"] * 1000))
            if track["artist"] and track["artist"] != artist_name:
                add(
                    f"{track_prefix}.artist_credit.names.0.name",
                    track["artist"],
                )
                add(
                    f"{track_prefix}.artist_credit.names.0.artist.name",
                    track["artist"],
                )
                add(
                    f"{track_prefix}.artist_credit.names.0.mbid",
                    track.get("mb_artistid"),
                )

    return fields


def prepare_release(
    album: Album,
    editor_url: str,
    lookup: Callable[[str], list[ArtistMatch] | None] | None = None,
    on_musicbrainz: bool | None = None,
) -> PreparedRelease:
    """Build a PreparedRelease for a beets album.

    Parameters
    ----------
    album:
        The album from the beets library. Must be loaded via the library so that
        ``album.items()`` resolves.
    editor_url:
        Url of the MusicBrainz release editor the data is prepared for.
    lookup:
        Callable that looks up an artist name in MusicBrainz and returns its
        matches (or None when the lookup is not possible). When None, artists
        without a stored MBID are marked as "unknown". Injected for tests.
    on_musicbrainz:
        Whether the album already exists on MusicBrainz (e.g. found via a
        barcode lookup). When None it is derived from a stored MBID.
    """
    tracks = _build_tracks(list(album.items()), album.albumartist or "")
    release = _build_release(album)
    exists = _clean(album.mb_albumid) is not None or (on_musicbrainz or False)
    flags = _build_flags(album, tracks, on_musicbrainz=exists)
    origin = _origin(editor_url)
    artists = build_artists(album, tracks, lookup=lookup, origin=origin)

    mbid_fields = _artist_mbid_field_keys(release, tracks)
    for artist in artists:
        artist["mbid_fields"] = mbid_fields.get(artist["name"], [])
        mbid = artist.get("mbid")
        if mbid:
            artist["artist_url"] = f"{origin}/artist/{mbid}"

    return PreparedRelease(
        album_id=int(album.id or 0),
        editor_url=editor_url,
        release=release,
        tracks=tracks,
        artists=artists,
        flags=flags,
        checklist=_build_checklist(album, release, tracks, flags),
        media_formats=sorted(MB_MEDIA_FORMATS),
        default_media_format=DEFAULT_MEDIA_FORMAT,
        countries=[
            CountryOption(code=code, name=name)
            for code, name in sorted(COUNTRIES.items(), key=lambda kv: kv[1])
        ],
        release_editor_fields=build_editor_fields(album, release, tracks),
    )
