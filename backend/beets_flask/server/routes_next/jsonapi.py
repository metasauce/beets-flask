"""Generic JSON:API-style types (the spec layer).

This is NOT a full JSON:API implementation, but a pragmatic subset:
- Focuses on ``data``, ``links`` and ``attributes``
- Related resources are referenced via ``relationships`` and can be
  embedded in full in ``included`` by passing ``include``
- Keeps typing strict and predictable for internal use

This module only contains the generic spec types. The concrete
attribute types and resource/document aliases of the endpoints live in
``beets/_types.py``, which plugs them into the generics of this module.

The types are pydantic models: quart-schema validates requests and
responses with them and generates the OpenAPI schemas from them. The
class docstrings become the schema descriptions, the ``Field``
annotations describe the fields; unset optional fields are serialized
as ``null``, keeping responses predictable.
"""

import inspect
from collections.abc import Callable
from functools import cache
from typing import Annotated, Any, Generic, NotRequired, TypedDict, TypeVar

from pydantic import BaseModel, Field
from quart_schema import validate_response

from beets_flask.server.exceptions import ApiException

A = TypeVar("A")
T = TypeVar("T", bound=str)
T_I = TypeVar("T_I", bound=str)

# ---------------------------------------------------------------------------- #
#                                 Core Objects                                 #
# ---------------------------------------------------------------------------- #


class LinkObject(BaseModel):
    """Pagination links of a response.

    ``self`` is the URL of the current page, ``next`` the URL of the
    following page (``null`` on the last page).
    """

    self: Annotated[
        str,
        Field(description="Canonical URL of the current resource/document"),
    ]
    next: Annotated[
        str | None, Field(description="URL for the next page (pagination)")
    ] = None


class MetaObject(BaseModel):
    """Additional information about a response.

    Currently only ``total``, the total number of results, is provided.
    """

    total: Annotated[
        int, Field(description="Total number of items available (for pagination)")
    ]


class ResourceIdentifier(BaseModel, Generic[T]):
    """A reference to a related resource.

    Related resources are not embedded in full, but referenced by their
    ``type`` and ``id``. Pass ``include`` to get the full resources in
    the ``included`` section of the response.
    """

    type: Annotated[T, Field(description="The type of the referenced resource")]
    id: Annotated[str, Field(description="The id of the referenced resource")]


class Resource(BaseModel, Generic[A, T]):
    """Primary resource object.

    This is the core unit of data returned by the API.
    """

    type: Annotated[T, Field(description="The resource type, e.g. ``item``")]
    id: Annotated[str, Field(description="The unique identifier of the resource")]
    attributes: Annotated[A, Field(description="The resource's attributes")]


R = TypeVar("R", bound=Resource)


class RelResource(Resource[A, T], Generic[A, T, T_I]):
    """A resource that references related resources."""

    relationships: Annotated[
        list[ResourceIdentifier[T_I]],
        Field(
            default_factory=list,
            description="References to related resources",
        ),
    ]


class SingleResourceDocument(BaseModel, Generic[R]):
    """Response containing a single resource."""

    data: Annotated[R, Field(description="The resource itself")]
    links: Annotated[
        LinkObject | None, Field(description="Pagination links of the response")
    ] = None
    meta: Annotated[
        MetaObject | None,
        Field(description="Additional information about the response"),
    ] = None


R_I = TypeVar("R_I", bound=Resource)


class SingleResourceDocumentWithIncluded(SingleResourceDocument[R], Generic[R, R_I]):
    """Single-resource response with embedded related resources."""

    included: Annotated[
        list[R_I] | None,
        Field(
            description=(
                "Related resources embedded in full, present when ``include`` was passed"
            )
        ),
    ] = None


class MultiResourceDocument(BaseModel, Generic[R]):
    """Response containing a list of resources."""

    data: Annotated[list[R], Field(description="The resources themselves")]
    links: Annotated[
        LinkObject | None, Field(description="Pagination links of the response")
    ] = None
    meta: Annotated[
        MetaObject | None,
        Field(description="Additional information about the response"),
    ] = None


class MultiResourceDocumentWithIncluded(MultiResourceDocument[R], Generic[R, R_I]):
    """Multi-resource response with embedded related resources."""

    included: Annotated[
        list[R_I] | None,
        Field(
            description=(
                "Related resources embedded in full, present when ``include`` was passed"
            )
        ),
    ] = None


# ------------------------------ Error handling ------------------------------ #


@cache
def _error_response_model(error_class: type[ApiException]) -> type[Any]:
    """Create the response model for an error class.

    The model mirrors :class:`SerializedException` but is named after the
    error class, so the docs show the specific error instead of a generic
    one. Its docstring is the error class' docstring; the openapi provider
    splits it into a compact response description (first line) and a
    schema description (remaining lines).
    """
    docstring = inspect.getdoc(error_class)
    # The class name is dynamic, so the functional form is required here.
    model = TypedDict(  # type: ignore[misc]  # noqa: UP013
        f"{error_class.__name__}",  # type: ignore[misc]
        {
            "type": Annotated[
                str,
                Field(description="The type of the error, i.e. the exception name"),
            ],
            "message": Annotated[
                str, Field(description="A human-readable error message")
            ],
            "description": NotRequired[
                Annotated[
                    str | None,
                    Field(description="Additional details about the error"),
                ]
            ],
            "trace": NotRequired[
                Annotated[
                    str | None,
                    Field(description="The stack trace of the error"),
                ]
            ],
        },
    )
    model.__doc__ = docstring or error_class.__name__
    return model


F = TypeVar("F")


def error_responses(*error_classes: type[ApiException]) -> Callable[[F], F]:
    """Document the error responses of a route in the openapi docs.

    Each exception class contributes one response via
    :func:`quart_schema.validation.validate_response`, using its
    :attr:`ApiException.status_code` as the HTTP status code and a body
    matching its serialized form, e.g.::

        @albums_bp.route("/<int:album_id>", methods=["GET"])
        @validate_response(SingleAlbumDocument)
        @error_responses(InvalidUsageException, NotFoundException)
        async def get_album(...): ...

    Parameters
    ----------
    error_classes:
        The exception classes the route can raise. Their ``status_code``
        determines the documented HTTP status code.
    """

    def decorator(func: F) -> F:
        for error_class in error_classes:
            func = validate_response(
                # The cached wrapper requires Hashable args; class objects are.
                _error_response_model(error_class),  # type: ignore[arg-type]
                status_code=error_class.status_code,
            )(func)
        return func

    return decorator
