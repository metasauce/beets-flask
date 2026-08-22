"""Validation helpers for the beets routes."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, get_origin, get_type_hints

from quart import current_app, request
from quart_schema.conversion import model_load
from quart_schema.typing import Model
from quart_schema.validation import (
    QUART_SCHEMA_QUERYSTRING_ATTRIBUTE,
    QuerystringValidationError,
)

# String values that count as boolean true when parsing query parameters.
_TRUE_VALUES = {"true", "1", "yes", "on"}


def validate_querystring(model_class: type[Model]) -> Callable:
    """Validate the request querystring, coercing boolean fields.

    Like :func:`quart_schema.validation.validate_querystring`, but query
    parameters arrive as strings, which msgspec refuses to convert to
    ``bool``. Fields typed as ``bool`` are therefore coerced first, so
    ``?delete_file=true`` validates against ``delete_file: bool``.
    """

    def decorator(func: Callable) -> Callable:
        setattr(func, QUART_SCHEMA_QUERYSTRING_ATTRIBUTE, model_class)
        hints = get_type_hints(model_class)
        bool_fields = {name for name, type_ in hints.items() if type_ is bool}
        # List-typed fields (e.g. ``filter_ids``) arrive as a single value
        # for ``?filter_ids=1`` and as multiple values for
        # ``?filter_ids=1&filter_ids=2``. Always pass a list so msgspec
        # accepts both forms.
        list_fields = {
            name for name, type_ in hints.items() if get_origin(type_) is list
        }

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request_args: dict[str, Any] = {
                key: (
                    request.args.getlist(key)
                    if len(request.args.getlist(key)) > 1 or key in list_fields
                    else request.args[key]
                )
                for key in request.args
            }
            for key in bool_fields & request_args.keys():
                values = request_args[key]
                if isinstance(values, list):
                    request_args[key] = [v.lower() in _TRUE_VALUES for v in values]
                else:
                    request_args[key] = values.lower() in _TRUE_VALUES
            model = model_load(
                request_args,
                model_class,
                QuerystringValidationError,
                decamelize=current_app.config["QUART_SCHEMA_CONVERT_CASING"],
                preference=current_app.config["QUART_SCHEMA_CONVERSION_PREFERENCE"],
            )
            return await current_app.ensure_async(func)(
                *args, query_args=model, **kwargs
            )

        return wrapper

    return decorator
