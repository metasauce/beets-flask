"""Lightweight JSON:API-style typing.

This is NOT a full JSON:API implementation, but a pragmatic subset:
- Focuses on `data`, `links`, and `attributes`
- Omits relationships, included, errors, etc.
- Keeps typing strict and predictable for internal use
"""

from typing import Annotated, Literal, NotRequired, TypedDict

from msgspec import Meta

# ---------------------------------------------------------------------------- #
#                                 Core Objects                                 #
# ---------------------------------------------------------------------------- #


class LinkObject(TypedDict, total=False):
    """Pagination links of a response.

    ``self`` is the URL of the current page, ``next`` the URL of the
    following page (absent on the last page).
    """

    self: Annotated[
        str, Meta(description="Canonical URL of the current resource/document")
    ]
    next: Annotated[str, Meta(description="URL for the next page (pagination)")]


class MetaObject(TypedDict, total=False):
    """Additional information about a response.

    Currently only ``total``, the total number of results, is provided.
    """

    total: Annotated[
        int, Meta(description="Total number of items available (for pagination)")
    ]


class ResourceIdentifier(TypedDict):
    """A reference to a related resource.

    Related resources are not embedded in full, but referenced by their
    ``type`` and ``id``. Pass ``include`` to get the full resources in
    the ``included`` section of the response.
    """

    type: Annotated[
        str, Meta(description="The type of the referenced resource, e.g. ``item``")
    ]
    id: Annotated[str, Meta(description="The id of the referenced resource")]


# ---------------------------------------------------------------------------- #
#                                     Items                                    #
# ---------------------------------------------------------------------------- #


class ItemAttributes(TypedDict, total=False):
    """Item Attributes"""

    title: Annotated[str | None, Meta(description="The title of the item")]


class ItemResource(TypedDict):
    """An item (track) of your music library.

    ``id`` is the item's id in the beets library, ``attributes``
    contains its metadata, e.g. the title.
    """

    type: Annotated[Literal["item"], Meta(description="The resource type")]
    id: Annotated[str, Meta(description="The item's id in the beets library")]
    attributes: Annotated[
        ItemAttributes,
        Meta(description="The item's attributes, e.g. its title"),
    ]


class SingleItemDocument(TypedDict):
    """The response of a request that returns a single item.

    The item is in ``data``.
    """

    data: Annotated[ItemResource, Meta(description="The item itself")]
    links: NotRequired[LinkObject]
    meta: NotRequired[MetaObject]


class MultiItemDocument(TypedDict):
    """The response of a request that returns multiple items.

    All items are in ``data``.
    """

    data: Annotated[list[ItemResource], Meta(description="The items themselves")]
    links: NotRequired[LinkObject]
    meta: NotRequired[MetaObject]


# ---------------------------------------------------------------------------- #
#                                    Albums                                    #
# ---------------------------------------------------------------------------- #


class AlbumAttributes(TypedDict, total=False):
    """Album Attributes"""

    title: Annotated[str, Meta(description="The title of the album")]


class AlbumResource(TypedDict):
    """An album of your music library.

    ``id`` is the album's id in the beets library, ``attributes``
    contains its metadata, e.g. the title. ``relationships`` references
    the album's items by ``type`` and ``id``.
    """

    type: Annotated[Literal["album"], Meta(description="The resource type")]
    id: Annotated[str, Meta(description="The album's id in the beets library")]
    attributes: Annotated[
        AlbumAttributes,
        Meta(description="The album's attributes, e.g. its title"),
    ]
    relationships: Annotated[
        list[ResourceIdentifier],
        Meta(description="The album's items, as ``type``/``id`` references"),
    ]


class SingleAlbumDocument(TypedDict):
    """The response of a request that returns a single album.

    The album is in ``data`` and its items are referenced in
    ``data.relationships``. Pass ``include=items`` to also embed the
    items in full in the ``included`` section.
    """

    data: Annotated[AlbumResource, Meta(description="The album itself")]
    included: Annotated[
        list[ItemResource],
        Meta(
            description="The album's items, present when ``include=items`` was passed"
        ),
    ]
    links: NotRequired[LinkObject]
    meta: NotRequired[MetaObject]


class MultiAlbumDocument(TypedDict):
    """The response of a request that returns multiple albums.

    The albums are in ``data``. Pass ``include=items`` to also embed
    their items in full in the ``included`` section.
    """

    data: Annotated[list[AlbumResource], Meta(description="The albums themselves")]
    included: NotRequired[
        Annotated[
            list[ItemResource],
            Meta(
                description="The albums' items, present when ``include=items`` was passed"
            ),
        ]
    ]
    links: NotRequired[LinkObject]
    meta: NotRequired[MetaObject]
