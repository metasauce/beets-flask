"""Concrete types of the beets library API endpoints.

The generic JSON:API spec layer lives in ``jsonapi.py``; this module
plugs the endpoint-specific attribute types into it.

Conventions (implemented in ``items.py`` / ``albums.py``):

- Resources have ``type``, ``id`` and ``attributes``
- Lists are paginated with ``links.next`` and ``meta.total``
- Related resources are referenced via ``relationships`` and can be
  embedded in full in ``included`` by passing ``include``
"""

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

from ..jsonapi import (
    MetaObject,
    MultiResourceDocument,
    MultiResourceDocumentWithIncluded,
    RelResource,
    Resource,
    SingleResourceDocument,
    SingleResourceDocumentWithIncluded,
)

# ---------------------------------------------------------------------------- #
#                                     Items                                    #
# ---------------------------------------------------------------------------- #


class ItemAttributes(BaseModel):
    """The attributes of an item (track).

    Used both for the ``attributes`` of an item resource in responses
    and as the accepted request body of the PATCH endpoints. Attributes
    that are not present in a PATCH body are left unchanged; an explicit
    ``null`` clears the field.

    Fields that are derived from the library state (``album_id``,
    ``added``, ``size``, ``path``, ``sources``) are read-only and
    ignored in PATCH bodies.
    """

    title: Annotated[str | None, Field(description="The title of the item")] = None
    artist: Annotated[str | None, Field(description="The artist of the item")] = None


class ItemResource(Resource[ItemAttributes, Literal["item"]]):
    """An item (track) of your music library.

    ``id`` is the item's id in the beets library, ``attributes``
    contains its metadata, e.g. the title.
    """


class SingleItemDocument(SingleResourceDocument[ItemResource]):
    """The response of a request that returns a single item."""


class MultiItemDocument(MultiResourceDocument[ItemResource]):
    """The response of a request that returns multiple items."""


# ---------------------------------------------------------------------------- #
#                                    Albums                                    #
# ---------------------------------------------------------------------------- #


class AlbumAttributes(BaseModel):
    """The attributes of an album.

    Used both for the ``attributes`` of an album resource in responses
    and as the accepted request body of the PATCH endpoints. Attributes
    that are not present in a PATCH body are left unchanged; an explicit
    ``null`` clears the field.

    ``sources`` is derived from the library state and ignored in PATCH
    bodies.
    """

    title: Annotated[str | None, Field(description="The title of the album")] = None
    albumartist: Annotated[
        str | None, Field(description="The album artist of the album")
    ] = None
    year: Annotated[int | None, Field(description="The release year of the album")] = (
        None
    )


class AlbumResource(RelResource[AlbumAttributes, Literal["album"], Literal["item"]]):
    """An album of your music library.

    ``id`` is the album's id in the beets library, ``attributes``
    contains its metadata, e.g. the title. ``relationships`` references
    the album's items by ``type`` and ``id``.
    """


class SingleAlbumDocument(
    SingleResourceDocumentWithIncluded[AlbumResource, ItemResource]
):
    """The response of a request that returns a single album.

    The album is in ``data`` and its items are referenced in
    ``data.relationships``. Pass ``include=items`` to also embed the
    items in full in the ``included`` section.
    """


class MultiAlbumDocument(
    MultiResourceDocumentWithIncluded[AlbumResource, ItemResource]
):
    """The response of a request that returns multiple albums."""


# ---------------------------------------------------------------------------- #
#                             Bulk query parameters                            #
# ---------------------------------------------------------------------------- #


class BulkResult(BaseModel):
    """The result of a bulk operation (e.g. update or delete).

    ``meta.total`` is the number of entities the operation was applied
    to.
    """

    meta: Annotated[
        MetaObject,
        Field(description="The number of entities the operation was applied to"),
    ]


class BulkFilterParams(TypedDict, total=False):
    """Query parameters shared by the bulk endpoints.

    The beets query string filter and/or the explicit ids filter; the
    two filters are combined with AND, and without either all entities
    match.
    """

    filter_query: Annotated[
        str,
        Field(
            description=(
                "Beets query string to filter the results, e.g. "
                "``artist:Tool``. Combined with ``filter_ids`` using AND."
            ),
            examples=["artist:Tool"],
        ),
    ]
    filter_ids: Annotated[
        list[int],
        Field(
            description=(
                "Only match entities with these ids. Repeat the parameter "
                "for multiple ids, e.g. ``filter_ids=1&filter_ids=2``. "
                "Combined with ``filter_query`` using AND."
            )
        ),
    ]
