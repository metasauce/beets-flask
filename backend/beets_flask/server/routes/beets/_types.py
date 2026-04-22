"""Lightweight JSON:API-style typing.

This is NOT a full JSON:API implementation, but a pragmatic subset:
- Focuses on `data`, `links`, and `attributes`
- Omits relationships, included, errors, etc.
- Keeps typing strict and predictable for internal use
"""

from typing import Generic, Literal, NotRequired, TypedDict, TypeVar

A = TypeVar("A")
T = TypeVar("T", bound=str)

# ---------------------------------------------------------------------------- #
#                                 Core Objects                                 #
# ---------------------------------------------------------------------------- #


class LinkObject(TypedDict, total=False):
    """Top-level pagination / navigation links.

    This is a simplified subset of JSON:API links.
    All fields are optional to allow flexible responses.
    """

    self: str  # Canonical URL of the current resource/document
    next: str  # URL for the next page (pagination)


class MetaObject(TypedDict, total=False):
    """Optional metadata container.

    Keep this intentionally small and extensible.
    """

    total: int  # Total number of items available (for pagination)


class ResourceIdentifier(TypedDict, Generic[T]):
    """Minimal reference to a resource (used in relationships)."""

    type: T
    id: str


class Resource(TypedDict, Generic[A, T]):
    """Primary resource object.

    This is the core unit of data returned by the API.
    """

    type: T  # Resource type (e.g. "items")
    id: str  # Unique identifier (string per JSON:API)
    attributes: A  # Domain-specific payload


T_I = TypeVar("T_I", bound=str)


class RelResource(Resource[A, T], Generic[A, T, T_I]):
    relationships: list[ResourceIdentifier[T_I]]


R = TypeVar("R", bound=Resource)


class SingleResourceDocument(TypedDict, Generic[R]):
    """Response containing a single resource."""

    data: R
    links: NotRequired[LinkObject]
    meta: NotRequired[MetaObject]


R_I = TypeVar("R_I", bound=Resource)


class SingleResourceDocumentWithIncluded(SingleResourceDocument[R], Generic[R, R_I]):
    included: NotRequired[list[R_I]]


class MultiResourceDocument(TypedDict, Generic[R]):
    """Response containing a list of resources."""

    data: list[R]
    links: NotRequired[LinkObject]
    meta: NotRequired[MetaObject]


class MultiResourceDocumentWithIncluded(MultiResourceDocument[R], Generic[R, R_I]):
    included: NotRequired[list[R_I]]


# ---------------------------------------------------------------------------- #
#                                     Items                                    #
# ---------------------------------------------------------------------------- #


class ItemAttributes(TypedDict, total=False):
    """Item Attributes"""

    title: str | None


ItemResource = Resource[ItemAttributes, Literal["item"]]
SingleItemDocument = SingleResourceDocument[ItemResource]
MultiItemDocument = MultiResourceDocument[ItemResource]

# ---------------------------------------------------------------------------- #
#                                    Albums                                    #
# ---------------------------------------------------------------------------- #


class AlbumAttributes(TypedDict, total=False):
    title: str


AlbumResource = RelResource[AlbumAttributes, Literal["album"], Literal["item"]]
SingleAlbumDocument = SingleResourceDocumentWithIncluded[AlbumResource, ItemResource]
MultiAlbumDocument = MultiResourceDocumentWithIncluded[AlbumResource, ItemResource]
