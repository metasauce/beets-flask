"""Artists endpoint.

Split artists by separators, and do some basic aggregation.
"""

import re
from typing import TYPE_CHECKING

import polars as pl
from quart import Blueprint, Response, g

from beets_flask.config import get_config
from beets_flask.server.exceptions import NotFoundException

artists_bp = Blueprint("artists", __name__)

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

# TODOs:
# Currently artist_sort is completely ignored. Im not even sure what it is supposed to do.
# Also artistids are not used, but they are in the database.


def artist_separators() -> list[str]:
    return get_config().data.gui.library.artist_separators


def split_pattern(separators: list[str]) -> str:
    return "|".join(map(re.escape, separators))


def get_artists_polars(table: str, artist: str | None = None) -> pl.LazyFrame:
    """Get all artists from the database using polars.

    Returns
    -------
        DataFrame with columns ['artist', 'count', 'last_added']
    """
    if table == "items":
        query = """
            SELECT
                artist,
                added
            FROM
                items
        """
    elif table == "albums":
        query = """
            SELECT
                albumartist AS artist,
                added

            FROM
                albums
        """
    else:
        raise ValueError(f"Invalid table name: {table}. Must be 'items' or 'albums'.")

    # Split the artist string by the specified separators
    artists: list[str] | None
    if len(artist_separators()) > 0 and artist is not None:
        artists = [
            a.strip() for a in re.split(split_pattern(artist_separators()), artist)
        ]
    elif artist is not None:
        artists = [artist.strip()]
    else:
        artists = None

    if artists is not None:
        # If an artist is specified, filter the query
        for i, a in enumerate(artists):
            if i == 0:
                query += f" WHERE instr(artist, ?) > 0"
            else:
                query += f" AND instr(artist, ?) > 0"

    with g.lib.transaction() as tx:
        rows = tx.query(query, artists) if artists else tx.query(query)

    if not rows:
        return pl.LazyFrame(
            schema={
                "artist": pl.Utf8,
                "count": pl.Int64,
                "last_added": pl.Int64,
                "first_added": pl.Int64,
            }
        )

    # Read from the database rows
    # TODO: We might be able to optimize the row loading to be lazy
    # could minimize the ram usage
    df = pl.LazyFrame(rows, schema=["artist", "added"], orient="row")

    # Convert added timestamps (beets stores as seconds, convert to milliseconds)
    df = df.with_columns((pl.col("added") * 1000).alias("added"))

    # Split artist strings into lists and explode into separate rows
    if len(artist_separators()) > 0:
        # split does not yet support regex...
        # see https://github.com/pola-rs/polars/issues/4819
        # we do a replace workaround
        df = df.with_columns(
            pl.col("artist")
            .str.replace_all("\uffff", "")
            .str.replace_all(split_pattern(artist_separators()), "\uffff")
            .str.split("\uffff")
        ).explode("artist")

    # Strip whitespace and process
    df = df.with_columns(pl.col("artist").str.strip_chars(), pl.col("added") * 1000)

    # Group by artist and aggregate using lazy operations
    df = df.group_by("artist").agg(
        pl.len().alias("count"),
        pl.col("added").max().alias("last_added"),
        pl.col("added").min().alias("first_added"),
    )

    if artists is not None:
        # If an artist is specified, filter the result
        pattern = split_pattern(artists)
        df = df.filter(pl.col("artist").str.contains(pattern, literal=False))
        # Overwrite if there are multiple artists (i.e. joined by a separator)
        if len(artists) > 1:
            df = df.with_columns(pl.lit(artist).alias("artist"))

    return df


# TODO: Pagination strategy
@artists_bp.route("/artists/<path:artist_name>", methods=["GET"])
@artists_bp.route("/artists", methods=["GET"], defaults={"artist_name": None})
async def all_artists(artist_name: str | None = None):
    """Get all artists from the database.

    This endpoint retrieves all artists from the database, splits them by
    specified separators and aggregates the data to count the number of items.
    """
    # Get lazy frames

    artists_albums_lazy = get_artists_polars("albums", artist_name)
    artists_items_lazy = get_artists_polars("items", artist_name)

    # Rename columns in lazy frames
    artists_albums_lazy = artists_albums_lazy.rename(
        {
            "count": "album_count",
            "last_added": "last_album_added",
            "first_added": "first_album_added",
        }
    )

    artists_items_lazy = artists_items_lazy.rename(
        {
            "count": "item_count",
            "last_added": "last_item_added",
            "first_added": "first_item_added",
        }
    )

    # Join lazy frames
    artists_lazy = artists_albums_lazy.join(
        artists_items_lazy,
        left_on="artist",
        right_on="artist",
        how="full",
        coalesce=True,
    )

    # Fill nulls and cast to int
    artists_lazy = artists_lazy.with_columns(
        pl.col("album_count").fill_null(0).cast(pl.Int64),
        pl.col("item_count").fill_null(0).cast(pl.Int64),
    )

    # Collect the result
    artists = artists_lazy.collect()

    if artist_name is not None:
        if artists.is_empty():
            raise NotFoundException(f"Artist '{artist_name}' not found.")
        else:
            return artists.row(0, named=True), 200
    # TODO: We serialize as records here it might be better to have a different structure as we send quite a bit of data
    return Response(artists.write_json(), mimetype="application/json")
