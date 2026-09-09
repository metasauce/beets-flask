from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..jsonapi import (
    RelResource,
    Resource,
    SingleResourceDocument,
    SingleResourceDocumentWithIncluded,
)

# ----------------------------------- Item ----------------------------------- #


class ItemAttributes(BaseModel):
    """The attributes of an item (track)."""

    title: Annotated[str | None, Field(description="The title of the item")] = None
    artist: Annotated[str | None, Field(description="The artist of the item")] = None


class ItemResource(Resource[ItemAttributes, Literal["item"]]):
    """An item (track) of your music library.

    ``id`` is the item's id in the beets library, ``attributes``
    contains the data from the beets library, e.g. the title.
    """


class SingleItemDocument(SingleResourceDocument[ItemResource]):
    """The response of a request that returns a single item."""


# ----------------------------------- Album ---------------------------------- #


class AlbumAttributes(BaseModel):
    """The attributes of an album."""

    album: Annotated[str | None, Field(description="The title of the album")] = None
    albumartist: Annotated[
        str | None, Field(description="The album artist of the album")
    ] = None
    year: Annotated[int | None, Field(description="The release year of the album")] = (
        None
    )


class AlbumResource(RelResource[AlbumAttributes, Literal["album"], Literal["item"]]):
    """An album of your music library.

    ``id`` is the album's id in the beets library, ``attributes``
    contains the data from the beets library, e.g. the title.
    ``relationships`` references the album's items by ``type`` and ``id``.
    """


class SingleAlbumDocument(
    SingleResourceDocumentWithIncluded[AlbumResource, ItemResource]
):
    """The response of a request that returns a single album.

    The album is in ``data`` and its items are referenced in
    ``data.relationships``. Pass ``include=items`` to also embed the
    items in full in the ``included`` section.
    """
