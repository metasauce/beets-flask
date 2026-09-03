"""Validation helpers for the API routes."""

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
    """Validate the request querystring, coercing boolean and list fields."""

    def decorator(func: Callable) -> Callable:
        setattr(func, QUART_SCHEMA_QUERYSTRING_ATTRIBUTE, model_class)

        hints = get_type_hints(model_class)
        bool_fields = {name for name, type_ in hints.items() if type_ is bool}
        list_fields = {
            name for name, type_ in hints.items() if get_origin(type_) is list
        }

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request_args: dict[str, Any] = {}

            for key in request.args:
                values = request.args.getlist(key)
                value: Any = (
                    values if len(values) > 1 or key in list_fields else values[0]
                )

                if key in bool_fields:
                    if isinstance(value, list):
                        value = [v.lower() in _TRUE_VALUES for v in value]
                    else:
                        value = value.lower() in _TRUE_VALUES

                request_args[key] = value

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
