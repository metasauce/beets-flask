import inspect
import traceback
from collections.abc import Awaitable, Callable
from functools import cache, wraps
from typing import Annotated, Any, NotRequired, ParamSpec, TypedDict, TypeVar

from msgspec import Meta
from quart_schema.validation import validate_response

from beets_flask.logger import log

T = TypeVar("T")


class SerializedException(TypedDict):
    """Serialized exception format.

    This is used to serialize exceptions to a common format.
    The format is as follows:
    {
        "type": "Exception type",
        "message": "Error message",
        "description": "Error description (optional)"
    }
    """

    type: str
    message: str
    description: NotRequired[str | None]
    trace: NotRequired[str | None]


class ApiException(Exception):
    """Base class for all API errors."""

    persist_in_db: bool
    """If true, the exception will be stored in the database on
    raise in sessions.
    TODO: Think about exception hierarchy.
    """
    status_code: int = 500

    def __init__(
        self, *args, status_code: int | None = None, persist_in_db: bool = True
    ):
        super().__init__(*args)
        if status_code is not None:
            self.status_code = status_code
        self.persist_in_db = persist_in_db


class InvalidUsageException(ApiException):
    """Invalid usage of the API."""

    status_code: int = 400


class NotFoundException(ApiException):
    """Resource not found.

    This is used to indicate that the requested resource was not found.
    """

    status_code: int = 404


class IntegrityException(ApiException):
    """Integrity error.

    This is used to indicate that the requested resource was not found.
    """

    status_code: int = 409


class NotImplementedException(ApiException):
    """Feature not implemented yet.

    The endpoint exists, but its functionality is not implemented yet.
    """

    status_code: int = 501


class NotImportedException(ApiException):
    """Not imported error.

    So far only used for the auto import session, when the best
    match is worse than the threshold.
    """

    status_code: int = 409


class NoCandidatesFoundException(ApiException):
    """No candidates found error.

    Raised when an online search does not return any candidates.
    Could be raised from automatic search (without searchid) but also when manually
    adding more candidates via interactive search (searchid given).
    """

    status_code: int = 409

    def __init__(
        self, *args, status_code: int | None = None, persist_in_db: bool = True
    ):
        if not args:
            error_text = "Lookup found no candidates. " + self.metadata_plugin_info()
            args = (error_text,)

        super().__init__(*args, status_code=status_code, persist_in_db=persist_in_db)

    @classmethod
    def metadata_plugin_info(cls) -> str:
        # Get enabled metadata source plugins to give a better error message
        error_text = ""
        try:
            from beets.metadata_plugins import find_metadata_source_plugins

            meta_plugins: list[str] = [
                p.data_source for p in find_metadata_source_plugins()
            ]
            if len(meta_plugins) > 0:
                error_text += f"Used '{', '.join(meta_plugins)}' as metadata source(s)."
            else:
                error_text += "No source plugins are enabled."

        except:
            error_text += "Could not determine enabled metadata source plugins."
        return error_text


class UserException(Exception):
    """Base class for errors caused by user input or config."""

    status_code: int = 422

    def __init__(self, *args, status_code: int | None = None):
        super().__init__(*args)
        if status_code is not None:
            self.status_code = status_code


class DuplicateException(UserException):
    """Duplicate error.

    Raised when we have trouble resolving duplicates in the beets library.
    Users should check their config and api usage.
    """

    status_code: int = 422


def error_responses(*error_classes: type[ApiException]) -> Callable[[T], T]:
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

    def decorator(func: T) -> T:
        for error_class in error_classes:
            func = validate_response(
                # The cached wrapper requires Hashable args; class objects are.
                _error_response_model(error_class),  # type: ignore[arg-type]
                status_code=error_class.status_code,
            )(func)
        return func

    return decorator


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
        f"{error_class.__name__}",
        {
            "type": Annotated[
                str,
                Meta(description="The type of the error, i.e. the exception name"),
            ],
            "message": Annotated[
                str, Meta(description="A human-readable error message")
            ],
            "description": NotRequired[
                Annotated[
                    str | None,
                    Meta(description="Additional details about the error"),
                ]
            ],
            "trace": NotRequired[
                Annotated[
                    str | None,
                    Meta(description="The stack trace of the error"),
                ]
            ],
        },
    )
    model.__doc__ = docstring or error_class.__name__
    return model


def to_serialized_exception(
    exception: Exception,
) -> SerializedException:
    """Convert an exception to a serialized format.

    Parameters
    ----------
    exception : Exception | None
        The exception to serialize.

    Returns
    -------
    SerializedException
        The serialized exception.
    """

    if exception is None:
        return None

    tb: str | None = None

    if exception.__traceback__ is not None:
        tb = "".join(traceback.format_tb(exception.__traceback__))

    return SerializedException(
        type=exception.__class__.__name__,
        message=str(exception),
        description=exception.__doc__,
        trace=tb,
    )


P = ParamSpec("P")  # Parameters
R = TypeVar("R")  # Return


def exception_as_return_value(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R | SerializedException]]:
    """Decorator to catch exceptions and return them as a values.

    This is used to catch exceptions in the redis worker and return them
    as a values we can use in the frontend. Sadly standard exeption handling
    in rq is lacking!
    """

    @wraps(f)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | SerializedException:
        try:
            return await f(*args, **kwargs)
        # Some exceptions are not serializable, so we need to convert them to a
        # serialized format. E.g. OSErrors
        except ApiException as e:
            log.info(e)
            return to_serialized_exception(e)
        except Exception as e:
            log.exception(e)
            return to_serialized_exception(e)

    return wrapper


__all__ = [
    "SerializedException",
    "ApiException",
    "InvalidUsageException",
    "NotFoundException",
    "IntegrityException",
    "NotImplementedException",
    "error_responses",
    "to_serialized_exception",
]
