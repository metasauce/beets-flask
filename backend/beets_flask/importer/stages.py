"""Beets-flask extends every stage in the normal beets import session.

This allows us to keep track of the import state and communicate it to the frontend.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Generator
from datetime import datetime
from functools import wraps
from inspect import isgenerator
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    TypeVarTuple,
    cast,
)

from beets import library, plugins
from beets.importer import (
    Action,
    ImportTask,
    SentinelImportTask,
)
from beets.importer.stages import (
    _extend_pipeline,
    _freshen_items,
)
from beets.importer.tasks import ImportTaskFactory
from beets.util import MoveOperation, bytestring_path, displayable_path
from beets.util import pipeline as beets_pipeline

from beets_flask import log
from beets_flask.server.exceptions import (
    NoCandidatesFoundException,
    NotImportedException,
)

from .progress import Progress, ProgressState
from .types import BeetsImportTask

if TYPE_CHECKING:
    from beets_flask.importer.session import (
        AutoImportSession,
        BaseSession,
        ImportSession,
    )
    from beets_flask.importer.types import BeetsItem

    from .pipeline import Stage

    # Tell type-checking that subclasses of BaseSession are allowed
    Session = TypeVar("Session", bound=BaseSession)


def skip_until(
    progress: Progress,
) -> Callable[
    [Callable[[Session, Task, *Arg], Ret]],
    Callable[[Session, Task, *Arg], Ret | Task],
]:
    """Decorater to skip all tasks with progress lower than the desired one.

    Needed to resume up a session without re-doing everything thats already contained
    in the state.

    Usage
    -----
    ```python
    @skip_until(Progress.READING_FILES)
    def read_task(session: BaseSessionNew, task: ImportTask):
        pass
    ```
    """

    def decorator(
        func: Callable[[Session, Task, *Arg], Ret],
    ) -> Callable[[Session, Task, *Arg], Ret | Task]:
        @wraps(func)
        def wrapper(session: Session, task: Task, *args: *Arg) -> Ret | Task:
            # Skip automatically if the task is already progressed
            # Note that >= and > below both have caveats:
            # >= might give us a too optimistic state if the function call fails
            # > might re-run the function if we resume, and we have not testet
            # what happens when doing the same state-mutation twice
            if not isinstance(task, ImportTask):
                log.warning(
                    f"Skipping {progress} for {task} as it is not an ImportTask"
                )
                return task

            # We set the progress before the stage runs, thus we need to compare
            # with - and redo - the previous progress.
            # Otherwise, we couldn't retry a stage once it crashed or was aborted.
            # For jobs that did not fail, we have extra progress levels (dummies) that
            # do not need any compute to redo. They are the most common point to resume
            # from (PREVIEW_COMPLETED in particular).
            prev_progress = session.state.upsert_task(task).progress
            if prev_progress > progress:
                log.debug(
                    f"Skipping {progress} for {task} because task progress {prev_progress=}"
                )
                return task

            log.debug(f"Skipped until encountered {progress} for {task}")
            return func(session, task, *args)

        return wrapper

    return decorator


def set_progress(
    before: Progress,
    after: Progress | None = None,
    on_error: dict[type[Exception], Progress] = {},
) -> Callable[
    [Callable[[Session, Task, *Arg], Ret]],
    Callable[[Session, Task, *Arg], Ret | Task],
]:
    """Decorater to set the progress of a task.

    Basically calls
    `session.set_progress(task, progress)`
    before the decorated function.

    Optionally, if an Exception is encountered while processing the task,
    another progress can be set (to account for later pipeline-steps, which will not
    take place). By default, we still raise.

    When combining, use after `skip_until()` decorator.

    Parameters
    ----------
    before: Progress
        Progress to set when (before) processing the task.
    after: Progress, optional
        Progress to set after processing the task. By default `before` is kept.
    on_error: dict[type[Exception], Progress], optional
        Mapping, which Progress to set for which Exception (instance check on the
        Exception). By default, if an exception occurs, the `before` Progress is kept.

    Usage
    -----
    ```python
    @set_progress(Progress.READING_FILES)
    def read_task(session: BaseSessionNew, task: ImportTask):
        pass

    @set_progress(
        Progress.LOOKING_UP_CANDIDATES,
        on_Error={NoCandidatesFoundException: Progress.PREVIEW_COMPLETED}
    )
    def lookup_candidates(session: BaseSessionNew, task: ImportTask):
        pass
    ```
    """

    def decorator(
        func: Callable[[Session, Task, *Arg], Ret],
    ) -> Callable[[Session, Task, *Arg], Ret | Task]:
        @wraps(func)
        def wrapper(session: Session, task: Task, *args: *Arg) -> Ret | Task:
            log.debug(f"Setting progress {before=} for {task}")

            session.set_task_progress(task, before)
            try:
                res = func(session, task, *args)
                if after is not None:
                    log.debug(f"Setting progress {after=} for {task}")
                    session.set_task_progress(task, after)
                return res
            except Exception as e:
                for e_to_handle, p in on_error.items():
                    if isinstance(e, e_to_handle):
                        log.debug(
                            f"Setting progress to {p} after Exception for {task} {e}"
                        )
                        session.set_task_progress(task, p)
                raise

        return wrapper

    return decorator


class StageOrder(dict):
    """An ordered dict of stages, mapping the stage name to its generator.

    Returned by each sessions `.stages` property.
    """

    def append(
        self,
        stage: Stage[ImportTask, Any],
        name: str | None = None,
    ):
        """Append a stage to the Order."""

        name = name or str(getattr(stage, "__name__", f"unknown_stage"))
        if name in self.keys():
            raise ValueError(f"Stage with name {name} already exists.")

        self[name] = stage

    def insert(
        self,
        stage: Stage[ImportTask, Any],
        name: str | None = None,
        after: str | None = None,
        before: str | None = None,
    ):
        """Insert a stage after or before another specific stage."""

        if after is None and before is None or (after and before):
            raise ValueError("Either `after` or `before` must be specified.")

        name = name or str(getattr(stage, "__name__", f"unknown_stage"))
        if name in self.keys():
            raise ValueError(f"Stage with name {name} already exists.")

        # even for the OrderedDict there is no insert at index method, so just rebuild
        keys = list(self.keys())
        values = list(self.values())

        idx = keys.index(after or before)  # type: ignore
        if after:
            idx += 1
        keys.insert(idx, name)
        values.insert(idx, stage)

        self.clear()
        self.update(zip(keys, values))


# --------------------------------- Decorator -------------------------------- #

Arg = TypeVarTuple("Arg")  # args und kwargs
Ret = TypeVar("Ret")  # return type
Task = TypeVar(
    "Task",
    bound=BeetsImportTask,
)  # task


def stage(
    func: Callable[[*Arg, Task], Ret | None],
):
    """Decorate a function to become a simple stage.

    Yields a task and waits until the next task is sent to it.

    >>> @stage
    ... def add(n, i):
    ...     return i + n
    >>> pipe = Pipeline([
    ...     iter([1, 2, 3]),
    ...     add(2),
    ... ])
    >>> list(pipe.pull())
    [3, 4, 5]
    """

    # use the wraps decorator to lift function name etc, we use this in StageOrder class
    @wraps(func)
    def coro(
        *args: *Arg,
    ) -> Generator[Ret | Task | None, Task, None]:
        # in some edge-cases we get no task. thus, we have to include the generic R
        task: Task | Ret | Generator[Task] | None = None
        while True:
            if isgenerator(task):
                for t in task:
                    task = yield t
            else:
                task = yield cast(
                    Task | None | Ret, task
                )  # wait for send to arrive. the first next() always returns None
            # yield task, call func which gives new task, yield new task in next()
            task = cast(Task, task)  # Slightly hacky, but we know task is a Task here
            task = func(*(args + (task,)))

    return coro


def mutator_stage(
    func: Callable[[*Arg, Task], Ret], name: str | None = None
) -> Callable[[*Arg], Generator[Ret | Task | None, Task, None]]:
    """Decorate a function that manipulates items in a coroutine to become a simple stage.

    Yields a task and waits until the next task is sent to it.

    >>> @mutator_stage
    ... def setkey(key, item):
    ...     item[key] = True
    >>> pipe = Pipeline([
    ...     iter([{'x': False}, {'a': False}]),
    ...     setkey('x'),
    ... ])
    >>> list(pipe.pull())
    [{'x': True}, {'a': False, 'x': True}]
    """

    @wraps(func)
    def coro(
        *args: *Arg,
    ) -> Generator[Ret | Task | None, Task, None]:
        task = None
        while True:
            task = yield task  # wait for send to arrive. the first next() always returns None
            # perform function on task, and in next() send the same, modified task
            # funcs prob. modify task in place?
            func(*(args + (task,)))

    return coro


# --------------------------------- Producer --------------------------------- #


def read_tasks(
    session: BaseSession,
):
    """Read the files from the paths and generate tasks.

    If the session already has tasks yield them.

    Adapted closely from beets, but we do not need/support resuming and skipping
    """

    log.debug(f"Reading files")

    # Our Skip-check usually uses Progress, but here we do not have progress yet
    # We want to catch the case when we resume a session,
    # where we manually add old tasks from disk.
    if len(session.state.tasks) > 0:
        for task in session.state.tasks:
            yield task
        return

    for toppath in session.paths:
        task_factory = ImportTaskFactory(toppath, session)
        for task in task_factory.tasks():
            if isinstance(task, SentinelImportTask):
                log.debug(f"Skipping {displayable_path(toppath)}")
                continue

            task_state = session.state.upsert_task(task)
            log.debug(f"Reading files from {displayable_path(toppath)}")
            task_state.set_progress(Progress.READING_FILES)
            yield task

        if not task_factory.imported:
            log.warning(f"No files imported from {displayable_path(toppath)}")


# ----------------------------- Transform Stages ----------------------------- #


def __group(item: library.Item) -> tuple[str, str]:
    return (item.albumartist or item.artist, item.album)


@stage
@skip_until(Progress.GROUPING_ALBUMS)
@set_progress(Progress.GROUPING_ALBUMS)
def group_albums(
    session: BaseSession,
    task: ImportTask,
) -> beets_pipeline.MultiMessage:
    """
    Groups items of the task into albums using their metadata.

    The groups are identified using artist and album fields.

    Creates a new Task for each found album, and removes the old task (and task_state)
    from the session.
    """

    # Split old task into multiple, and only keep new ones!
    session.state.remove_task(task)

    tasks: list[ImportTask] = []
    sorted_items = sorted(task.items, key=__group)
    for _, _items in itertools.groupby(sorted_items, __group):
        items = list(_items)  # Consume the iterator to a list
        task = ImportTask(task.toppath, [i.path for i in items], items)
        tasks += task.handle_created(session)

    # handle the beets-flask specific states
    for task in tasks:
        session.state.upsert_task(task)

    # FIXME: Not really sure we need this tbh, see also task.skip
    # tasks.append(SentinelImportTask(task.toppath, task.paths))

    return beets_pipeline.MultiMessage(tasks)


@mutator_stage
@skip_until(Progress.LOOKING_UP_CANDIDATES)
@set_progress(
    Progress.LOOKING_UP_CANDIDATES,
    on_error={NoCandidatesFoundException: Progress.PREVIEW_COMPLETED},
)
def lookup_candidates(
    session: BaseSession,
    task: ImportTask,
):
    """Performing the initial MusicBrainz lookup for an album.

    We tweaks this from upstream beets to not
    call `task.lookup_candidates()` but instead `session.lookup_candidates(task)`,
    with some extra logic

    This is more consistent, as it allows the logic
    to be modified by each kind of session.

    Calls `task.lookup_candidates()`,
    which sets attributes of the task:
        - cur_artist   # metadata in file
        - cur_album
        - candidates
        - rec
    """
    if task.skip:
        # FIXME This gets duplicated a lot. We need a better
        # abstraction.
        return

    # FIXME: what happens with our new skip logic and plugins?
    plugins.send("import_task_start", session=session, task=task)

    session.lookup_candidates(task)


@mutator_stage
@skip_until(Progress.IDENTIFYING_DUPLICATES)
@set_progress(before=Progress.IDENTIFYING_DUPLICATES, after=Progress.PREVIEW_COMPLETED)
def identify_duplicates(
    session: BaseSession,
    task: ImportTask,
):
    """Stage to identify which candidates would be duplicates if imported."""
    if task.skip:
        return

    session.identify_duplicates(task)


@stage
@skip_until(Progress.WAITING_FOR_USER_SELECTION)
@set_progress(Progress.WAITING_FOR_USER_SELECTION)
def user_query(
    session: ImportSession,
    task: ImportTask,
) -> ImportTask | beets_pipeline.MultiMessage | Literal["__PIPELINE_BUBBLE__"]:
    """A coroutine for interfacing with the user about the tagging process.

    The coroutine accepts an ImportTask objects. It uses the
    session's `choose_match` method to determine the `action` for
    this task. Depending on the action additional stages are executed
    and the processed task is yielded.

    It emits the ``import_task_choice`` event for plugins. Plugins have
    access to the choice via the ``task.choice_flag`` property and may
    choose to change it.
    """

    if task.skip:
        return task

    if session.already_merged(task.paths):
        # For some reason the type hinter does not like this without cast
        return cast(Literal["__PIPELINE_BUBBLE__"], beets_pipeline.BUBBLE)

    # Ask the user for a choice.
    # This calls session.choose_match(task)... but whyyy?
    task.choose_match(session)
    plugins.send("import_task_choice", session=session, task=task)

    # TODO: Import as singletons i.e. task.choice_flag is action.TRACKS

    # As albums: group items by albums and create task for each album
    if task.choice_flag is Action.ALBUMS:
        log.warning("This should never run via beets-flask!")
        return _extend_pipeline(
            [task],
            group_albums(session),
            lookup_candidates(session),
            user_query(session),
        )

    # Note: this checks the global config for the default action.
    found_duplicates = task.find_duplicates(session.lib)
    # Different than vanilla beets, we do not use a stage for duplicate resolution,
    # as it only calls the sessions method, anyway.
    session.resolve_duplicate(task, found_duplicates)

    if task.should_merge_duplicates:
        # Create a new task for tagging the current items
        # and duplicates together
        duplicate_items = task.duplicate_items(session.lib)

        # Duplicates would be reimported so make them look "fresh"
        _freshen_items(duplicate_items)
        duplicate_paths = [item.path for item in duplicate_items]

        # Record merged paths in the session so they are not reimported
        session.mark_merged(duplicate_paths)

        merged_task = ImportTask(
            None, task.paths + duplicate_paths, task.items + duplicate_items
        )
        return _extend_pipeline(
            [merged_task], lookup_candidates(session), user_query(session)
        )

    _apply_choice(session, task)

    return task


# Dynamicly set_progress for plugin name
# e.g. DetailedProgress(Progress.EARLY_IMPORT, plugin_name="my_plugin")
@mutator_stage
def plugin_stage(
    session: BaseSession,
    func: Callable[[BaseSession, ImportTask], None],
    progress: ProgressState,
    task: ImportTask,
):
    # TODO: Skip if already progressed
    session.set_task_progress(task, progress)
    if task.skip:
        return

    log.debug(f"Running plugin stage {func.__name__}")
    func(session, task)
    log.debug(f"Finished plugin stage {func.__name__}")

    task.reload()
    log.debug(f"Reload plugin stage done {func.__name__}")


@mutator_stage
@skip_until(Progress.MATCH_THRESHOLD)
@set_progress(
    Progress.MATCH_THRESHOLD,
    on_error={NotImportedException: Progress.PREVIEW_COMPLETED},
)
def match_threshold(
    session: AutoImportSession,
    task: ImportTask,
):
    """Stage to determine if a match is good enough to be auto-imported."""
    if task.skip:
        log.debug(f"Skipping task: {session=}, {task=}")
        return task

    session.match_threshold(task)


# --------------------------------- Consumer --------------------------------- #


@stage
@skip_until(Progress.MANIPULATING_FILES)
@set_progress(before=Progress.MANIPULATING_FILES, after=Progress.IMPORT_COMPLETED)
def manipulate_files(
    session: BaseSession,
    task: ImportTask,
) -> ImportTask:
    """A coroutine (pipeline stage) that performs necessary file.

    manipulations *after* items have been added to the library and
    finalizes each task.
    """
    if not task.skip:
        if task.should_remove_duplicates:
            task.remove_duplicates(session.lib)

        if session.config["copy"]:
            operation = MoveOperation.COPY
        # elif session.config["move"]:
        #     operation = MoveOperation.MOVE
        # elif session.config["link"]:
        #     operation = MoveOperation.LINK
        # elif session.config["hardlink"]:
        #     operation = MoveOperation.HARDLINK
        # elif session.config["reflink"] == "auto":
        #     operation = MoveOperation.REFLINK_AUTO
        # elif session.config["reflink"]:
        #     operation = MoveOperation.REFLINK
        # else:
        #     operation = None
        else:
            log.warning(
                "Beets-flask does not yet support other import modes than 'copy'. "
                + "Please consider updating your config."
            )
            operation = MoveOperation.COPY

        task.manipulate_files(session, operation, write=session.config["write"])

    # Progress, cleanup, and event.
    task.finalize(session)

    # Cleanup of duplicates. After successful import, we do not want the candidates
    # to have duplicate-info anymore. The reason is that if we undo the import,
    # there wont be any duplicates in the library. Also, we dont want to show
    # the duplicate-badge for things that were imported.
    # TODO: outlook: add new badges for what has been done with duplicates?
    task_state = session.state.get_task_state_for_task_raise(task)
    chosen_candidate = task_state.chosen_candidate_state
    if chosen_candidate:
        chosen_candidate.duplicate_ids = []
        # We remove duplicate info from all candidates.
        # Although this causes the frontend to possibly not show the duplicate
        # actions, that is fine: Upon re-import, we raise a duplicate action error,
        # which is shown to the user, and then the duplicate actions will appear.

    if task_state.toppath is not None and len(session.state.task_states) == 1:
        # If we have only one task and no toppath this indicates that we are
        # operating on a temp directory we override the toppath
        # to the session's folder path.
        task.toppath = bytestring_path(session.state.folder_path)

    return task


@stage
def finalize(
    session: BaseSession,
    task: ImportTask,
) -> ImportTask:
    """Give our custom sessions a way to do something at the very end."""
    session.finalize(task)
    return task


def _apply_choice(session: ImportSession, task: ImportTask):
    # tweaked version of beets apply_choices.
    # we do not want to rely on the global config object
    # (in particular, the set_fields, because we always want to set gui_import_id).
    # see the original:
    # from beets.importer import apply_choice

    if task.skip:
        return

    # Change metadata.
    if task.apply:
        task.apply_metadata()
        plugins.send("import_task_apply", session=session, task=task)

    # We need to reinsert items into the db if they were removed earlier
    item: BeetsItem
    for item in task.imported_items():
        item._db = session.lib
        item.album_id = None
        item.id = None

    task.add(session.lib)
    task.set_fields(session.lib)

    # copy of core logic from set_fields()
    items: list[BeetsItem] = task.imported_items()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_state = session.state.get_task_state_for_task_raise(task)
    with session.lib.transaction():
        for item in items:
            item.set_parse("gui_import_id", task_state.id)
            item.set_parse("gui_import_date", timestamp)
            item.store()
        task.album.set_parse("gui_import_id", task_state.id)
        task.album.set_parse("gui_import_date", timestamp)
        task.album.store()


__all__ = [
    "read_tasks",
    "group_albums",
    "lookup_candidates",
    "identify_duplicates",
    "user_query",
    "plugin_stage",
    "manipulate_files",
]
