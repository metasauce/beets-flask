"""Beets pipeline overloads.

Added type hints to decorators because it is annoying to have to look up
the type of the function usage.

This is a temporary implementation. Async Generators are an antipattern
(use coroutines instead). We only use them here because the older beets pipeline
used Generators, and we still rely on parts of it.
"""

import asyncio
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    Coroutine,
    Generator,
    Iterable,
    Sequence,
)
from typing import (
    Any,
    Literal,
    TypeVar,
)

from beets.util.pipeline import MultiMessage, _allmsgs

# Generics for Generators
Y = TypeVar("Y")  # yield
S = TypeVar("S")  # send
R = TypeVar("R")  # return

# --------------------------------- Pipeline --------------------------------- #

# yield : Task or None, send : Task, return : None
Task = TypeVar("Task", bound=Any)
Stage = (
    Generator[Task | MultiMessage | Literal["__PIPELINE_BUBBLE__"] | None, Task, R]
    | AsyncGenerator[Task | None, Task]
)


class AsyncPipeline[Task: Any, R]:
    start_tasks: AsyncIterable[Task]
    stages: list[Stage[Task, R]]

    # Original: stages = [start_task, *stages]
    def __init__(
        self,
        start_tasks: Iterable[Task] | AsyncIterable[Task] | Task,
        stages: Sequence[Stage[Task, R]] = [],
    ) -> None:
        if isinstance(start_tasks, Iterable):
            self.start_tasks = _async_iterable_from_iterable(start_tasks)
        elif isinstance(start_tasks, AsyncIterable):
            self.start_tasks = start_tasks
        else:
            self.start_tasks = _async_iterable_from_iterable([start_tasks])

        self.stages = list(stages)

    def add_stage(self, *stage: Stage[Task, R]) -> None:
        """Add a stage to the pipeline."""
        for s in stage:
            self.stages.append(s)

    async def pull_async(self) -> AsyncGenerator[Task, None]:
        """Pull items through the pipeline.

        If item is coroutine, await it.
        """
        # Priming -> Wait for first send i.e. right side of `task = yield`
        for stage in self.stages:
            await _next_resolve_async(stage)

        async for task in self.start_tasks:
            msgs: list[Task] = _allmsgs(task)  # returns a list of tasks

            for stage in self.stages:
                next_coros: list[Coroutine] = [
                    _send_resolve_async(stage, msg) for msg in msgs
                ]
                # override for input of next stage
                msgs = []
                for out in await asyncio.gather(*next_coros):
                    msgs.extend(_allmsgs(out))

            for msg in msgs:
                yield msg

    async def run_async(self) -> None:
        """Run the pipeline asynchronously.

        This just resolves the generator.
        """
        async for _ in self.pull_async():
            # resolves the generator, and awaits each element after the previous
            pass


async def _next_resolve_async[Y, S, R](gen: Generator[Y, S, R] | AsyncGenerator[Y, S]):
    """Call next on the generator."""
    if isinstance(gen, Generator):
        return next(gen)
    else:
        return await anext(gen)


async def _send_resolve_async[Y, S, R](
    gen: Generator[Y, S, R] | AsyncGenerator[Y, S], *args, **kwargs
):
    """Send to the generator."""
    if isinstance(gen, Generator):
        return gen.send(*args, **kwargs)
    else:
        return await gen.asend(*args, **kwargs)


async def _async_iterable_from_iterable[Task: Any](
    iterable: Iterable[Task],
) -> AsyncIterable[Task]:
    for item in iterable:
        yield item
