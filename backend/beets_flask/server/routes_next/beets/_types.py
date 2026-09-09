from dataclasses import dataclass
from functools import cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from beets_flask import log
from beets_flask.server.exceptions import InvalidUsageError

from ..jsonapi import (
    RelResource,
    Resource,
    SingleResourceDocument,
    SingleResourceDocumentWithIncluded,
)


@dataclass(frozen=True)
class ReadOnly:
    """Marker for a field that is read-only and cannot be modified."""

    value: bool = True


class BaseAttributes(BaseModel):
    """Base class for resource attributes.

    Attributes that are not present in a PATCH body are left unchanged; an explicit
    ``null`` clears the field.
    """

    @classmethod
    @cache
    def readonly_fields(cls) -> set[str]:
        return {
            name
            for name, field in cls.model_fields.items()
            if any(isinstance(metadata, ReadOnly) for metadata in field.metadata)
        }

    def patch_data(self) -> dict[str, object]:
        """Construct a dict of attributes to update from the request body.

        Only includes attributes that are present in the request body and not read-only.
        Absent attributes are left unchanged; an explicit ``null`` clears the field.

        Basically the converter to beets' ``item.update()`` or ``album.update()``.
        """

        readonly_fields = type(self).readonly_fields()

        # ``model_fields_set`` are the attributes present in the request body:
        # absent fields are left unchanged, an explicit ``null`` clears.
        update_data: dict[str, object] = {}
        for key in self.model_fields_set:
            if key in readonly_fields:
                log.warning(
                    f"Attempt to update read-only attribute {key!r} in PATCH body. "
                    "This attribute will be ignored."
                )
                continue

            update_data[key] = getattr(self, key)

        if not update_data:
            raise InvalidUsageError("No attributes to update")

        return update_data


# ----------------------------------- Item ----------------------------------- #


class ItemAttributes(BaseAttributes):
    """The attributes of an item (track).

    Used both for the ``attributes`` of an item resource in responses and as the
    accepted request body of the PATCH endpoints.

    Attributes that are not present in a PATCH body are left unchanged; an explicit
    ``null`` clears the field.
    """

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


class AlbumAttributes(BaseAttributes):
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
