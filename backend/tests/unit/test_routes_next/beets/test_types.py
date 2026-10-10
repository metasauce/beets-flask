import pytest

from beets_flask.server.routes_next.beets._types import (
    Direction,
    ItemSortField,
    Sort,
)


class TestSort:
    """Tests for ``Sort.from_str``."""

    @pytest.mark.parametrize(
        "sort_string, field, direction",
        [
            ("-added", ItemSortField.ADDED, Direction.DESC),
            ("-year", ItemSortField.YEAR, Direction.DESC),
            ("+title", ItemSortField.TITLE, Direction.ASC),
            # No prefix defaults to ascending.
            ("added", ItemSortField.ADDED, Direction.ASC),
            ("artist", ItemSortField.ARTIST, Direction.ASC),
            ("-albumartist", ItemSortField.ALBUMARTIST, Direction.DESC),
            ("-album", ItemSortField.ALBUM, Direction.DESC),
            ("+bitrate", ItemSortField.BITRATE, Direction.ASC),
        ],
        ids=[
            "desc_added",
            "desc_year",
            "asc_title",
            "bare_added",
            "bare_artist",
            "desc_albumartist",
            "desc_album",
            "asc_bitrate",
        ],
    )
    def test_item_parse(
        self, sort_string: str, field: ItemSortField, direction: Direction
    ):
        """Parse a sort string into its field and direction."""
        parsed = Sort[ItemSortField].from_str(sort_string)

        assert parsed.field == field
        assert parsed.direction == direction

    @pytest.mark.parametrize(
        "sort_string",
        ["", "-", "+", "bogus", "-bogus", "year,-title", "--year", " YEAR"],
        ids=[
            "empty",
            "only_minus",
            "only_plus",
            "unknown_field",
            "unknown_desc",
            "multi_key",
            "double_sign",
            "leading_space",
        ],
    )
    def test_invalid(self, sort_string: str):
        """Reject malformed sort strings."""
        with pytest.raises(ValueError):
            Sort[ItemSortField].from_str(sort_string)
