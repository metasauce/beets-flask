from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from beets_flask import log
from beets_flask.server.exceptions import InvalidUsageError

from ..jsonapi import (
    MultiResourceDocument,
    MultiResourceDocumentWithIncluded,
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


class ItemSortField(StrEnum):
    """The fields that items can be sorted by in the bulk endpoints.

    Single source of truth for the sortable fields: the ``sort`` query
    parameter of the items bulk endpoints accepts these fields,
    optionally prefixed with ``+`` (ascending) or ``-`` (descending);
    :class:`ItemSortField` parametrizes :class:`Sort` for the items
    endpoint, :meth:`values` provides the
    bare names, and the frontend type is generated from it via py2ts.
    """

    ADDED = "added"
    YEAR = "year"
    TITLE = "title"
    ARTIST = "artist"
    ALBUMARTIST = "albumartist"
    ALBUM = "album"
    TRACK = "track"
    DISC = "disc"
    LENGTH = "length"
    BITRATE = "bitrate"

    @classmethod
    def values(cls) -> list[str]:
        """The bare sortable field names, e.g. ``["added", "year", …]``."""
        return [field.value for field in cls]


class ItemResource(Resource[ItemAttributes, Literal["item"]]):
    """An item (track) of your music library.

    ``id`` is the item's id in the beets library, ``attributes``
    contains the data from the beets library, e.g. the title.
    """


class SingleItemDocument(SingleResourceDocument[ItemResource]):
    """The response of a request that returns a single item."""


class MultiItemDocument(MultiResourceDocument[ItemResource]):
    """The response of a request that returns multiple items."""


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


class AlbumSortField(StrEnum):
    """The fields that albums can be sorted by in the bulk endpoint.

    Parametrizes :class:`Sort` for the albums endpoint; ``added`` is the
    default sort (newest first).
    """

    ADDED = "added"
    ALBUM = "album"
    ALBUMARTIST = "albumartist"
    YEAR = "year"

    @classmethod
    def values(cls) -> list[str]:
        """The bare sortable field names."""
        return [field.value for field in cls]


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


class MultiAlbumDocument(
    MultiResourceDocumentWithIncluded[AlbumResource, ItemResource]
):
    """The response of a request that returns multiple albums."""


# ---------------------------------- Common ---------------------------------- #


class BulkFilterQueryParams(BaseModel):
    """The filter query parameters for the bulk endpoints."""

    filter_query: str | None = Field(
        None,
        description="A beets query string to filter the results, e.g. `year:2020`. For "
        "more infomration see the [beets query syntax]"
        "(https://beets.readthedocs.io/en/latest/reference/query.html).",
    )
    filter_ids: list[int] | None = Field(
        None,
        description="A list of beets ids to filter by, e.g. `1,2,3`.",
    )


# ---------------------------------- Cursor ---------------------------------- #


class Direction(StrEnum):
    """The direction of sorting."""

    ASC = "+"
    DESC = "-"


class Sort[F: StrEnum](BaseModel):
    """Base of the endpoint sort models, parametrized over the sort-field enum.

    E.g. ``Sort[ItemSortField]`` sorts the items of the items endpoint.
    :meth:`from_str` parses the ``+field`` / ``-field`` ``sort`` query
    parameter into a sort instance.
    """

    field: F
    direction: Direction = Direction.ASC

    @classmethod
    def from_str(cls, s: str) -> Sort:
        """Parse a sort string like ``+title`` or ``-artist``."""
        if not s:
            raise ValueError("Sort string cannot be empty")

        direction = Direction.ASC
        if s[0] in (Direction.ASC, Direction.DESC):
            direction = Direction(s[0])
            s = s[1:]

        # The sort-field enum of the parametrization, e.g. ItemSortField.
        field_enum = cls.model_fields["field"].annotation
        try:
            field = field_enum(s)
        except ValueError:
            raise ValueError(f"Invalid sort field: {s!r}")

        return cls(field=field, direction=direction)


class Cursor[S: Sort](BaseModel):
    """Keyset cursor that encodes the full query state.

    Carries the page's ``sort`` (a sort model parametrized over the
    endpoint's field enum, e.g. ``Sort[ItemSortField]``), the filters,
    and the last seen row
    (``last_value``/``last_id``) anchoring the next page. An unanchored
    cursor (without ``last_value``/``last_id``) returns the first page.

    The token format is the model itself: :meth:`to_string` dumps the model
    (``exclude_none``) to an opaque base64 token; :meth:`from_string`
    validates it back into ``Cursor[...]``, so tampered tokens (e.g. an
    unknown sort field) are rejected by pydantic.
    """

    sort: S
    filter_query: str | None = None
    filter_ids: list[int] | None = None
    last_value: str | None = None
    last_id: int | None = None

    def next(self, last_value: str | None, last_id: int) -> Cursor:
        """The anchored cursor for the page after ``last_value``/``last_id``."""
        return self.model_copy(update={"last_value": last_value, "last_id": last_id})

    def to_string(self) -> str:
        """Serialize the cursor to an opaque, URL-safe base64 token."""
        return self._b64encode(self.model_dump_json(exclude_none=True).encode())

    @classmethod
    def from_string(cls, token: str) -> Cursor:
        """Deserialize a token produced by :meth:`to_string`.

        Raises
        ------
        ValueError
            If the token is not valid base64/JSON.

        """
        try:
            payload = json.loads(cls._b64decode(token))
        except Exception as exc:
            raise ValueError(f"Invalid cursor string: {token}") from exc
        return cls.model_validate(payload)

    @staticmethod
    def _b64encode(raw: bytes) -> str:
        """URL-safe base64 without padding."""
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _b64decode(token: str) -> bytes:
        """Decode URL-safe base64, tolerating missing padding."""
        return base64.urlsafe_b64decode(token.encode() + b"=" * (-len(token) % 4))
