from typing import Any, Protocol, TypeVar

B = TypeVar("B")  # beets type
M = TypeVar("M")  # model type


class Context:
    """Shared mapping context used during bidirectional conversion.

    This context provides identity-based caching to avoid duplicate
    object reconstruction and to preserve reference consistency
    during recursive mappings.
    """

    def __init__(self):
        self.from_cache: dict[int, Any] = {}
        self.to_cache: dict[int, Any] = {}


class BeetsMapper(Protocol[B, M]):
    """Protocol for bidirectional mapping between Beets objects and models.

    This mapper provides cached conversion in both directions:
    - Beets → Model via `from_beets`
    - Model → Beets via `to_beets`

    Identity-based caching (via `id()`) ensures:
    - stable object graphs during recursive mapping
    - prevention of infinite recursion
    - consistent reuse of already-mapped instances

    Subclasses must implement:
    - `_from_beets`
    - `_to_beets`
    """

    def from_beets(self, obj: B, ctx: Context) -> M:
        """Convert a Beets object into a model instance with caching."""
        key = id(obj)
        if key in ctx.from_cache:
            return ctx.from_cache[key]

        result = self._from_beets(obj, ctx)
        ctx.from_cache[key] = result
        return result

    def to_beets(self, model: M, ctx: Context) -> B:
        """Convert a model instance back into a Beets object with caching."""
        key = id(model)
        if key in ctx.to_cache:
            return ctx.to_cache[key]

        result = self._to_beets(model, ctx)
        ctx.to_cache[key] = result
        return result

    def _from_beets(self, obj: B, ctx: Context) -> M:
        """Implement Beets → model conversion."""
        raise NotImplementedError

    def _to_beets(self, model: M, ctx: Context) -> B:
        """Implement model → Beets conversion."""
        raise NotImplementedError
