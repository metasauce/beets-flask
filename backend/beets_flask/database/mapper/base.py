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


class DBMapper(Protocol[B, M]):
    """Protocol for bidirectional mapping between Beets objects and models.

    This mapper provides cached conversion in both directions:
    - Beets|LiveState → Model via `to_db`
    - Model → Beets|LiveState via `from_db`

    Identity-based caching (via `id()`) ensures:
    - stable object graphs during recursive mapping
    - prevention of infinite recursion
    - consistent reuse of already-mapped instances

    Subclasses must implement:
    - `_to_db`
    - `_from_db`

    This solves the following problem:
    Consider we want to deserialize a Task with Candidates C1 and C2, where
    C1 and C2 hold references to the task and vice versa.
    - C1(ref to Task)
    - C2(ref to Task)
    - Task(C1,C2)
    We dont want to create copies of the objects, references only!
    The mapper avoids drilling and thinking about this more than necessary :)
    """

    def to_db(self, obj: B, ctx: Context) -> M:
        """Convert a Beets object into a model instance with caching."""
        key = id(obj)
        if key in ctx.to_cache:
            return ctx.to_cache[key]

        model = self._to_db(obj, ctx)
        ctx.to_cache[key] = model
        return model

    def from_db(self, model: M, ctx: Context) -> B:
        """Convert a model instance back into a Beets object with caching."""
        key = id(model)
        if key in ctx.from_cache:
            return ctx.from_cache[key]

        # Backward-compatible single-phase path
        obj = self._from_db(model, ctx)
        ctx.from_cache[key] = obj
        return obj

    def _to_db(self, obj: B, ctx: Context) -> M:
        """Implement Beets → model conversion."""
        raise NotImplementedError

    def _from_db(self, model: M, ctx: Context) -> B:
        """Implement model → Beets conversion."""
        raise NotImplementedError
