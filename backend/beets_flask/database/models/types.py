from __future__ import annotations

import json
from array import array
from typing import Any

from sqlalchemy import types


class DictType(types.TypeDecorator):
    """Stores a dict[str, Any] as a JSON-encoded string in the database.

    Allows for flexible storage of dictionaries with string keys and values of
    any (serializable) type.
    """

    impl = types.Text
    cache_ok = True

    allowed_keys_types: tuple[type, ...] = (str,)
    allowed_values_types: tuple[type | Any, ...] = (Any,)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Value must be a dict")

        # Any type needs some special handling
        allowed_types_v: tuple[type, ...] = tuple(
            filter(lambda x: x is not Any, self.allowed_values_types)
        )

        if not len(allowed_types_v) == 0:
            if not all(isinstance(v, allowed_types_v) for v in value.values()):
                raise ValueError(
                    f"Value must be a dict with values of type {allowed_types_v}. Got: {value.values()}"
                )

        if not all(isinstance(k, self.allowed_keys_types) for k in value.keys()):
            raise ValueError(f"Keys must be of type {self.allowed_keys_types}.")

        return json.dumps({str(k): v for k, v in value.items()})

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)

    def copy(self, **kw):
        return self.__class__(self.impl.length)  # type: ignore


class IntDictType(DictType):
    """Stores a dict[int, int] as a JSON-encoded string in the database."""

    allowed_keys_types = (int,)
    allowed_values_types = (int,)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return {int(k): int(v) for k, v in json.loads(value).items()}


class StrDictType(DictType):
    """Stores a dict[str, str] as a JSON-encoded string in the database."""

    allowed_keys_types = (str,)
    allowed_values_types = (str,)


class FloatListType(types.TypeDecorator):
    """Stores a list[float] as binary using array.array ('d' = float64)."""

    impl = types.LargeBinary
    cache_ok = True

    def process_bind_param(
        self, value: list[float] | None, dialect: Any
    ) -> bytes | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("Value must be a list")
        if not all(isinstance(v, int | float) for v in value):
            raise ValueError(f"All values must be float, got: {value}")
        arr = array("d", value)
        return arr.tobytes()

    def process_result_value(
        self, value: bytes | None, dialect: Any
    ) -> list[float] | None:
        if value is None:
            return None
        arr = array("d")
        arr.frombytes(value)
        return arr.tolist()

    def copy(self, **kw: Any) -> FloatListType:
        return self.__class__()
