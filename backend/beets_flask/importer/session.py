"""
Session classes for the import pipeline.

Sessions often take particular arguments, such as a duplicate action. In the simplest and most common case,
each session has one task (i.e. one album) to deal with. Sometimes, however, one session may have multiple tasks,
such as when one folder contains files from two albums.

To account for this, we use the TaskMapping type.
They contain an action to take for each task (mapping a task_id as string to the action), and the default value
must be None (which means that the session uses the default action for that task, loaded from user config).

When no mapping is given, the default action is used for all tasks.

```
TaskIdMappingArg = defaultdict[str, T | None] | None
```

If you want to pass a value to all tasks, you can omit looking up the task ids and
instead use "*" as the key, which will apply the action to all tasks of the session.

```
action_for_all : TaskIdMappingArg[DuplicateAction] = {"*": "remove"}
```
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypedDict, TypeGuard, TypeVar

import nest_asyncio
from beets import autotag, importer, plugins
from beets.ui import UserError, _open_library
from beets.util import bytestring_path
from deprecated import deprecated

from beets_flask.config import get_config
from beets_flask.disk import is_archive_file
from beets_flask.importer.progress import Progress, ProgressState
from beets_flask.importer.types import (
    BeetsAlbum,
    BeetsLibrary,
    DuplicateAction,
)
from beets_flask.logger import log
from beets_flask.server.exceptions import (
    ApiException,
    DuplicateException,
    IntegrityException,
    NoCandidatesFoundException,
    NotImportedException,
    to_serialized_exception,
)
from beets_flask.utility import capture_stdout_stderr

from .pipeline import AsyncPipeline
from .stages import (
    StageOrder,
    finalize,
    group_albums,
    identify_duplicates,
    lookup_candidates,
    manipulate_files,
    match_threshold,
    plugin_stage,
    read_tasks,
    user_query,
)
from .states import ProgressState, SessionState

nest_asyncio.apply()

# ---------------------------------------------------------------------------- #
#                               Types and helpers                              #
# ---------------------------------------------------------------------------- #

T = TypeVar("T")

TaskIdMapping = defaultdict[str, T]
TaskIdMappingArg = dict[str, T | None] | None


def parse_task_id_mapping(mapping: TaskIdMappingArg[T], default: T) -> TaskIdMapping[T]:
    """
    Convert the flexible arguments to stricter TaskIdMapping that sessions use internally.

    Parameters
    ----------
    mapping : TaskIdMappingArg
        For each task_id (key) which action to take (value).
        If None, the default action is used for all tasks.
        If "*" is used as key, this action is used for all tasks, and only one key-value
        pair is allowed.
    default : T
        Default value to use for all tasks that are not in the mapping, or "*".


    Note
    ----
    TaskIdMappings are defaultdicts, which keeps the lower level logic simpler.
    TaskIdMappingsArgs are just dicts, which are serializable trhough api and redis
    thread bounds.
    """

    m: TaskIdMapping[T] = defaultdict(lambda: default)
    if mapping is not None:
        if "*" in mapping.keys():
            if len(mapping) > 1:
                raise ValueError(
                    "If you use '*' as key, you cannot use any other keys in the mapping."
                )
            else:
                return defaultdict(lambda: mapping["*"] or default)

        for k, v in mapping.items():
            if v is None:
                continue
            m[k] = v

    return m


class CandidateChoiceFallback(Enum):
    """
    Type for the candidate choice.

    Candidate Choices are either a string (the candidate id) or a special case
    (asis candidate, or the best one).
    """

    ASIS = 1
    BEST = 2


CandidateChoice = str | CandidateChoiceFallback


class Search(TypedDict):
    """Search for a candidate.

    This is used to search for a candidate in the preview session.
    """

    search_ids: list[str]
    search_artist: str | None
    search_album: str | None


def _is_search(d: Any) -> TypeGuard[Search]:
    """Check if the given dict is a Search object."""
    return (
        d is not None
        and isinstance(d, dict)
        and "search_ids" in d
        and isinstance(d["search_ids"], list)
    )


# ---------------------------------------------------------------------------- #
#                                   Sessions                                   #
# ---------------------------------------------------------------------------- #


class BaseSession(importer.ImportSession, ABC):
    """Base class for our GUI-based ImportSessions.

    Operates on single Albums / files.

    Parameters
    ----------
    path : list[str]
        list of album folders to import
    config_overlay : str or dict
        path to a config file to overlay on top of the default config.
        Note that if `dict`, the lazyconfig notation e.g. `{import.default_action: skip}`
        wont work reliably. Better nest the dicts: `{import: {default_action: skip}}`

    Note: It's a design choice to require that you manually create and pass the
    `SessionState` object. Usually the states go into the database, which needs explizit
    handling beyond the session.
    """

    # attributes needed to create a beetsTag instance for our database
    # are contained in the associated SessionState -> TaskState -> CandidateStates
    state: SessionState

    pipeline: AsyncPipeline[importer.ImportTask, Any] | None = None
    config_overlay: dict

    lib: BeetsLibrary

    def __init__(
        self,
        state: SessionState,
        config_overlay: dict | None = None,
    ):
        if not state.path.exists():
            raise FileNotFoundError(f"Path {state.path} does not exist.")
        if state.path.is_file() and not is_archive_file(state.path):
            raise ValueError(
                f"Path {state.path} is not an archive file. "
                + "Importing singletons is not supported yet."
            )

        # FIXME: This is a super bad convention of the original beets.
        # We do not want to pollute a global config object every time a session runs.
        # This is fine for the cli tool, where each run creates only one session
        # but not for our long-running webserver.
        config = get_config().beets_config
        if isinstance(config_overlay, dict):
            config.set_args(config_overlay)

        self.config_overlay = config_overlay or {}
        self.state = state

        super().__init__(
            lib=_open_library(config),
            paths=[bytestring_path(state.path)],
            query=None,
            loghandler=None,
        )
        # Hacky workaround to use our logging, to allow plugins to communicate
        self.logger.handlers = log.handlers
        log.debug(f"Created new {self.__class__.__name__} for {state.path}")

    @property
    def path(self) -> Path:
        return self.state.path

    @deprecated
    def run_and_capture_output(self) -> tuple[str, str]:
        """Run the import session and capture the output.

        Uses the original beets import session run method,
        with lots of overhead.
        Sets self.preivew to output and error messages occuring during run.

        Returns
        -------
            tuple[str, str]: out, err
        """
        self.logger.debug(f"{self.paths}")
        out, err, _ = capture_stdout_stderr(self.run)
        self.preview = out + "\n\n" + err if err else out
        return out, err

    def get_config_value(self, key: str, type_func: Callable | None = None) -> Any:
        """Get a config value from the overlay or default.

        TODO: remove or rework, this is finicky, and we should be able to come up
        with something better now that we have our own config class.

        Use dots to separate levels.
        """

        path = key.split(".")

        overlay = self.config_overlay
        for p in path:
            overlay = overlay.get(p, {})

        # overlay takes priority
        if not isinstance(overlay, dict):
            return type_func(overlay) if type_func else overlay

        # get settings from user settings, this is not a dict, but confuse config
        # the confuse config views do not throw key errors, and their .get() is not
        # the same as dict.get(), but rather resolves the value.
        default = get_config().beets_config
        for p in path:
            default = default[p]
        default = default.get(type_func) if type_func else default.get()
        return default

    # -------------------------- State handling helpers -------------------------- #

    def set_task_progress(
        self, task: importer.ImportTask, progress: ProgressState | Progress | str
    ):
        """Set the progress for a task belonging to the session.

        If string is given it is set as the message of the current progress.
        Note: currently we only implement status on the level of the whole import session,
        but should eventually do this per selection (task).
        """

        task_state = self.state.get_task_state_for_task_raise(task)

        task_state.set_progress(progress)

    def get_task_progress(self, task: importer.ImportTask) -> ProgressState | None:
        """Get the progress of the task, via this sessions state."""
        task_state = self.state.get_task_state_for_task(task)
        return task_state.progress if task_state else None

    # -------------------------------- Stages -------------------------------- #

    @property
    @abstractmethod
    def stages(self) -> StageOrder:
        """Set the stages for the session.

        In Subclasses, define the order of stages here.
        """
        raise NotImplementedError("Implement in subclass")

    def resolve_duplicate(self, task: importer.ImportTask, found_duplicates):
        """Overload default resolve duplicate and skip it.

        This basically skips this stage.
        """
        self.logger.warning(
            "Skipping duplicate resolution. "
            + f"Your session should implement this! -> {self.__class__.__name__}"
        )
        task.set_choice(importer.Action.SKIP)

    def choose_item(self, task: importer.ImportTask):
        """Overload default choose item and skip it.

        This session should not reach this stage.
        """
        self.logger.debug(f"skipping choose_item {task}")
        return importer.Action.SKIP

    def should_resume(self, path):
        """Overload default should_resume and skip it.

        Should normally be no problem if the config is set correctly, but just
        in case.
        """
        self.logger.debug(f"skipping should_resume {path}")
        return False

    def identify_duplicates(self, task: importer.ImportTask):
        """For all candidates, check if they have duplicates in the library.

        This stage should only be run for preview sessions, but we still have
        some old code in stages.py/user_query().
        """
        raise NotImplementedError(
            f"This session should not reach this stage. {self.__class__.__name__}"
        )

    def lookup_candidates(self, task: importer.ImportTask):
        """Lookup candidates for the task.

        This stage should only be run for preview sessions, but we still have
        some old code in stages.py/user_query().
        """
        raise NotImplementedError(
            f"This session should not reach this stage. {self.__class__.__name__}"
        )

    def finalize(self, task: importer.ImportTask):
        """Last stage called and customizable any session."""
        if len(self.config_overlay) > 0:
            # make sure we dont leave overlays in beets
            # but for multi-task sessions, this might break overlays for remaining tasks
            get_config().commit_to_beets()
        self.logger.debug(f"Finalized {self} {task}")

    # ---------------------------------- Run --------------------------------- #

    def run_sync(self) -> SessionState:
        """Run the import session synchronously."""
        return asyncio.run(self.run_async())

    async def run_async(self) -> SessionState:
        """Run the import session asynchronously.

        Does not set tasks to completed at the end.
        Take care of this in subclasses.
        """
        # For now, until we improve the upstream beets config logic,
        # adhere to importer.ImportSession convention and create a local copy
        # of the config.
        config = get_config().beets_config
        self.set_config(config["import"])

        # TODO: check some config values. that are not compatible with our code.
        self.pipeline = AsyncPipeline(start_tasks=read_tasks(self))

        for s in self.stages.values():
            self.pipeline.add_stage(s)

        log.info(f"Running {self.__class__.__name__} on state<{self.state.id=}>.")
        log.debug(f"Running {len(self.pipeline.stages)} stages.")

        # reset exception state
        # TODO: To clear or not to clear,
        # exception hierarchy and own table for exceptions/warnings
        # self.state.exc = None
        plugins.send("import_begin", session=self)
        try:
            assert self.pipeline is not None
            await self.pipeline.run_async()
        except importer.ImportAbortError:
            log.debug(f"Interactive import session aborted by user")
        except ApiException as e:
            if e.persist_in_db:
                log.debug(f"Persisting exception {e} in session state")
                self.state.exc = to_serialized_exception(e)
            raise e
        except Exception as e:
            self.state.exc = to_serialized_exception(e)
            raise e

        log.info(f"Completed {self.__class__.__name__} on state<{self.state.id=}>.")
        return self.state


class PreviewSession(BaseSession):
    """Preview what would be imported. Only fetches candidates."""

    group_albums: bool | None
    autotag: bool | None

    def __init__(
        self,
        state: SessionState,
        config_overlay: dict | None = None,
        group_albums: bool | None = None,
        autotag: bool | None = None,
        **kwargs,
    ):
        """
        Create new PreviewSession.

        Parameters
        ----------
        group_albums : bool | None
            Whether to create multple tasks, one for each album found in the metadata
            of the files. Set to true if you have multiple albums in a single folder.
            If None: get value from beets config.
        autotag : bool | None
            Whether to look up metadata online. If None: get value from beets config.
        """

        super().__init__(state, config_overlay, **kwargs)
        self.group_albums = group_albums
        self.autotag = autotag

    # -------------------------------- Stages -------------------------------- #

    @property
    def stages(self) -> StageOrder:
        stages = StageOrder()

        if self.get_config_value("import.singletons"):
            # beets tweaks the album grouping settings via overlay for singletons.
            raise NotImplementedError("Singletons not implemented yet.")

        if self.group_albums or (
            self.group_albums is None and self.get_config_value("import.group_albums")
        ):
            stages.append(group_albums(self))

        if self.autotag or (
            self.autotag is None and self.get_config_value("import.autotag")
        ):
            stages.append(lookup_candidates(self))

        stages.append(identify_duplicates(self))
        stages.append(finalize(self))

        return stages

    # --------------------------- Stage Definitions -------------------------- #

    def identify_duplicates(self, task: importer.ImportTask):
        """For all candidates, check if they have duplicates in the library."""
        task_state = self.state.get_task_state_for_task_raise(task)

        for idx, cs in enumerate(
            task_state.candidate_states + [task_state.asis_candidate]
        ):
            # This is a mutable operation i.e. candidate state is modfied here!
            duplicates = cs.identify_duplicates(self.lib)

            if len(duplicates) > 0:
                log.debug(f"Found duplicates for {cs.id=}: {duplicates}")

    def lookup_candidates(self, task: importer.ImportTask):
        """Lookup candidates for the task."""

        search_ids = self.config["search_ids"].as_str_seq()  # might be an empty list
        log.debug(
            f"Looking up candidates for {task.paths}, using search ids {search_ids}"
        )

        task.lookup_candidates(search_ids)

        if len(task.candidates) == 0:
            raise NoCandidatesFoundException(persist_in_db=True)

        # Update our state
        task_state = self.state.get_task_state_for_task_raise(task)
        task_state.add_candidates(task.candidates)


class AddCandidatesSession(PreviewSession):
    """
    Preview session that adds a candidate to the ones already fetched.

    Can only run on a session state of a preview session that already has
    candidates.
    """

    search: TaskIdMapping[Search | Literal["skip"]]
    initial_task_states: dict[str, ProgressState]

    def __init__(
        self,
        state: SessionState,
        config_overlay: dict | None = None,
        search: TaskIdMappingArg[Search | Literal["skip"]] = None,
        **kwargs,
    ):
        super().__init__(state, config_overlay, **kwargs)

        # None means skip search for this task
        self.search = parse_task_id_mapping(search, "skip")
        self.initial_task_states = {}

        for task in self.state.task_states:
            self.initial_task_states[task.id] = deepcopy(task.progress)
            if task.progress >= Progress.PREVIEW_COMPLETED:
                # Reset task progress only for tasks that have search values
                # other tasks are skipped
                # This should only be relevant for searches on multiple tasks
                # (i.e. folders)
                s = self.search[task.id]
                if s != "skip":
                    task.set_progress(Progress.LOOKING_UP_CANDIDATES - 1)

    def lookup_candidates(self, task: importer.ImportTask):
        """Amend the found candidate to the already existing candidates (if any)."""
        # see ref in lookup_candidates in beets/importer.py

        task_state = self.state.get_task_state_for_task_raise(task)
        search = self.search[task_state.id]

        if search == "skip":
            log.debug(f"Skipping search for {task_state.id=}")
            return

        # Beets treats empty strings like real strings, which is not what we want here.
        # TODO: revisit once PR merged upstream: https://github.com/beetbox/beets/pull/6117
        if (
            search["search_artist"] is not None
            and search["search_artist"].strip() == ""
        ):
            search["search_artist"] = None
        if search["search_album"] is not None and search["search_album"].strip() == "":
            search["search_album"] = None
        search["search_ids"] = list(
            filter(lambda x: x.strip() != "", search["search_ids"])
        )

        log.debug(f"Using {search=} for {task_state.id=}, {task_state.paths=}")

        try:
            _, _, prop = autotag.tag_album(
                task.items,
                search_ids=search["search_ids"],
                search_album=search["search_album"],
                search_artist=search["search_artist"],
            )
        except Exception as e:
            # TODO: With beets 2.6.0 this should be revisited
            # since beets should than be able to handle these exceptions
            # gracefully upstream.
            # https://github.com/beetbox/beets/pull/5965
            from beetsplug.musicbrainz import MusicBrainzAPIError
            from beetsplug.spotify import APIError as SpotifyAPIError

            if isinstance(e, MusicBrainzAPIError):
                raise NoCandidatesFoundException(
                    f"Failed to contact Musicbrainz API: {e.get_message()}",
                    persist_in_db=False,
                )
            elif isinstance(e, SpotifyAPIError):
                raise NoCandidatesFoundException(
                    f"Failed to contact Spotify API: {e}",
                    persist_in_db=False,
                )
            else:
                raise NoCandidatesFoundException(
                    f"Failed to contact online APIs.",
                    persist_in_db=False,
                )

        task_state.add_candidates(prop.candidates)

        # Update quality of best candidate, likely not needed for us, only beets cli.
        task.rec = max(prop.recommendation, task.rec or autotag.Recommendation.none)

        if len(prop.candidates) == 0:
            error_text = "Search found no candidates via "
            if search["search_ids"]:
                error_text += f"ids: {', '.join(search['search_ids'])}; "
            if search["search_artist"]:
                error_text += f"artist: {search['search_artist']}; "
            if search["search_album"]:
                error_text += f"album: {search['search_album']}; "
            error_text += NoCandidatesFoundException.metadata_plugin_info()
            raise NoCandidatesFoundException(
                error_text,
                persist_in_db=False,
            )
        # Hack: Clear exception if we found new candidates
        elif (
            self.state.exc is not None
            and self.state.exc["type"] == "NoCandidatesFoundException"
        ):
            log.debug(
                "Clearing previous NoCandidatesFoundException after finding candidates via search."
            )
            self.state.exc = None

    def finalize(self, task: importer.ImportTask):
        """Restore initial taks and session states."""

        task_state = self.state.get_task_state_for_task_raise(task)
        if task_state.id in self.initial_task_states:
            task_state.set_progress(self.initial_task_states[task_state.id])
        else:
            log.warning(
                f"Task {task_state.id} not in initial task states. "
                + "Cannot restore previous progress."
            )

        super().finalize(task)


class ImportSession(BaseSession):
    """
    Import session that assumes we already have a match-id.

    Needs to run from an already finished Preview Session.
    """

    candidate_ids: TaskIdMapping[CandidateChoice]
    duplicate_actions: TaskIdMapping[DuplicateAction]

    def __init__(
        self,
        state: SessionState,
        config_overlay: dict | None = None,
        candidate_ids: TaskIdMappingArg[CandidateChoice] = None,
        duplicate_actions: TaskIdMappingArg[DuplicateAction] = None,
    ):
        """Create new ImportSession.

        Parameters
        ----------
        candidate_ids : optional
            Either id of candidate(s) or the import choice. This is used to determine which
            candidate to import. If a dict is given, the keys are the task ids and the
            values are the candidate ids. You can also use the import choice enum
            `ImportChoice.ASIS` or `ImportChoice.BEST` to indicate that you want to
            import the candidate as-is or the best candidate.
            FIXME: at the moment asis is broken
        duplicate_actions : str
            The action to take if duplicates are found. One of "skip", "keep",
            "remove", "merge", "ask". If None, the default is read from
            the user config and applied to all tasks.
        """

        config_overlay = {} if config_overlay is None else config_overlay
        if config_overlay.get("import", {}).get("search_ids") is not None:
            raise ValueError("search_ids set in config_overlay. This is not supported.")

        super().__init__(state, config_overlay)

        # Create a mapping for the duplicate action
        # each task might have a different action.
        # if none is given the default action is used from the config
        default_action: DuplicateAction = self.get_config_value(
            "import.duplicate_action", str
        )
        self.duplicate_actions = parse_task_id_mapping(
            duplicate_actions, default_action
        )

        # For candidates, None means to take best
        self.candidate_ids = parse_task_id_mapping(
            candidate_ids, CandidateChoiceFallback.BEST
        )

    async def run_async(self) -> SessionState:
        # only allow import sessions to run on preview states (not other import states)
        if self.state.progress == Progress.IMPORT_COMPLETED:
            log.error(
                f"Cannot run {self.__class__.__name__} from states that already "
                + f"completed an import. (i.e. other imports) [{self.state.progress}]"
            )
            e = UserError("Cannot redo imports. Try undo and/or retag!")
            self.state.exc = to_serialized_exception(e)
            raise e
        elif self.state.progress > Progress.PREVIEW_COMPLETED:
            log.warning(
                f"Resetting state from {self.state.progress} to PREVIEW_COMPLETED for "
                + f"import session {self.state.id}."
            )
            for task in self.state.task_states:
                task.set_progress(Progress.PREVIEW_COMPLETED)

        state = await super().run_async()

        # Trigger cli_exit event to have compatibility with beets plugin that
        # execute after the import is completed.
        plugins.send("cli_exit", lib=self.lib)
        return state

    # ------------------------------ Stages ------------------------------ #

    @property
    def stages(self):
        stages = StageOrder()

        # FIXME: user_query calls task.choose_match, which calls session.choose_match.
        # Better abstraction needed upstream.
        stages.append(user_query(self))

        # Early import stages
        plugs = plugins.find_plugins()
        for p in plugs:
            for stage in p.get_early_import_stages():
                stages.append(
                    plugin_stage(
                        self,
                        stage,
                        ProgressState(
                            Progress.EARLY_IMPORTING,
                            plugin_name=stage.__name__,
                        ),
                    ),
                    name=f"early_plugin_stage_{p.__class__.__name__}_{stage.__name__}",
                )

        # Import stages
        for p in plugs:
            for stage in p.get_import_stages():
                stages.append(
                    plugin_stage(
                        self,
                        stage,
                        ProgressState(
                            Progress.IMPORTING,
                            plugin_name=stage.__name__,
                        ),
                    ),
                    name=f"plugin_stage_{p.__class__.__name__}_{stage.__name__}",
                )

        # finally, move files
        stages.append(manipulate_files(self))
        stages.append(finalize(self))

        return stages

    def finalize(self, task: importer.ImportTask):
        """
        Reset previous match threshold exceptions.

        Needed because we might run a normal ImportSession manually after
        the AutoImportSession. The AutoImportSession needs to keep an Exception in its
        status to inform the frontend, which we need to clear here.
        (No need to override `finalize` in AutoImportSession, despite it inherriting
        from here, because it raises when below threshold).
        """
        if (
            self.state.exc is not None
            and self.state.exc["type"] == "NotImportedException"
            and self.state.exc["message"].startswith("Match below threshold")
        ):
            log.debug(
                "Clearing previous MatchThresholdException after successful import."
            )
            self.state.exc = None
        super().finalize(task)

    # --------------------------- Stage Definitions -------------------------- #

    def choose_match(self, task: importer.ImportTask):
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug(f"choose_match {task}")

        task_state = self.state.get_task_state_for_task_raise(task)

        # Pick the candidate to import
        candidate_id = self.candidate_ids[task_state.id]

        if isinstance(candidate_id, str):
            candidate_state = task_state.get_candidate_state_by_id(candidate_id)
            if candidate_state is None:
                raise ValueError(f"Candidate with id {candidate_id} not found.")
        elif candidate_id == CandidateChoiceFallback.BEST:
            candidate_state = task_state.best_candidate_state
            if candidate_state is None:
                raise ValueError(f"No candidate found.")
        elif candidate_id == CandidateChoiceFallback.ASIS:
            candidate_state = task_state.asis_candidate
        else:
            raise NotImplementedError("ImportChoice.ASIS not implemented yet.")

        # update task_state to keep track of the choice in the database
        task_state.chosen_candidate_state_id = candidate_state.id
        log.debug(
            f"Setting chosen candidate for task {task_state.id} to {candidate_state.id}"
        )

        # Let plugins display info
        results = plugins.send("import_task_before_choice", session=self, task=task)
        actions = [action for action in results if action]

        if len(actions) > 0:
            # decide if we can just move past this and ignore the plugins
            raise UserError(
                f"Plugins returned actions, which is not supported for {self.__class__.__name__}"
            )

        # ASIS
        if candidate_state.id == task_state.asis_candidate.id:
            log.debug(f"Importing {task} as-is")
            return importer.Action.ASIS

        return candidate_state.match

    def resolve_duplicate(
        self, task: importer.ImportTask, found_duplicates: list[BeetsAlbum]
    ):
        log.debug(
            f"Resolving duplicates for {task} with action {self.duplicate_actions}"
        )

        if len(found_duplicates) == 0:
            log.debug(f"No duplicates found for")
            return

        task_state = self.state.get_task_state_for_task_raise(task)
        task_duplicate_action = self.duplicate_actions[task_state.id]
        task_state.duplicate_action = task_duplicate_action
        match task_duplicate_action:
            case "skip":
                task.set_choice(importer.Action.SKIP)
            case "keep":
                pass
            case "remove":
                task.should_remove_duplicates = True
            case "merge":
                task.should_merge_duplicates = True
            case "ask":
                # task.set_choice(importer.action.SKIP)
                raise DuplicateException(
                    "You have set the duplicate action to 'ask' in your beets config."
                )
            case _:
                raise DuplicateException(
                    f"Unknown duplicate action: {self.duplicate_actions}"
                )


class BootlegImportSession(ImportSession):
    """
    Import session to import without modifying metadata.

    No preview session required.

    Essentially `beet import --group-albums -A`, ideal for bootlegs and
    just getting a folder into your library where you are sure the metadata is correct.
    """

    def __init__(
        self,
        state,
        config_overlay: dict | None = None,
        **kwargs,
    ):
        """Create new ImportAsIsSession.

        Parameters
        ----------
        state: SessionState
            Preconfigured state of the import session.
        config_overlay : dict
            Configuration to overlay on top of the default config.
            "import.group_albums", "import.autotag" and "import.search_ids" are ignored.
        **kwargs
            See `ImportSession`.
        """

        config_overlay = {} if config_overlay is None else deepcopy(config_overlay)
        import_overlay = config_overlay.get("import", {})

        if "group_albums" in import_overlay and import_overlay["group_albums"] is False:
            log.warning("Overwriting 'group_albums' in config_overlay.")
        if "autotag" in import_overlay and import_overlay["autotag"] is True:
            log.warning("Overwriting 'autotag' in config_overlay.")
        if "search_ids" in import_overlay:
            log.warning("Overwriting 'search_ids' in config_overlay.")

        import_overlay["group_albums"] = True
        import_overlay["autotag"] = False
        import_overlay["search_ids"] = None

        config_overlay["import"] = import_overlay

        super().__init__(state, config_overlay, **kwargs)

        # overwrite the default action for all tasks
        self.candidate_ids = parse_task_id_mapping(
            {"*": CandidateChoiceFallback.ASIS},
            CandidateChoiceFallback.ASIS,
        )

    @property
    def stages(self):
        stages = super().stages
        stages.insert(before="user_query", stage=group_albums(self))
        return stages


class AutoImportSession(ImportSession):
    """Generate a preview and import if the best match is good enough.

    Preview generation is skipped if the provided session state already has a preview.

    Wether the import is triggered depends on the specified `import_threshold`, or
    the beets-config setting `match.strong_rec_thresh`.
    The match quality is calculated via penalties, thus it ranges from 0 to 1, but a
    perfect match is at 0. The same convention is used for thresholds.

    The default threshold is 0.04, so that a "96% match or better" will be imported.

    Raises a `NotImportedException` if the match quality is worse than the threshold,
    stopping the pipeline.
    """

    import_threshold: float

    def __init__(
        self,
        state,
        config_overlay: dict | None = None,
        import_threshold: float | None = None,
        **kwargs,
    ):
        """Create new AutoImportSession.

        Parameters
        ----------
        state: SessionState
            Preconfigured state of the import session.
        config_overlay : optional, dict
            Configuration to overlay on top of the default config.
        import_threshold: optional, float
            0 to import only perfect matches, 1 to import everything. Default is 0.04.
        **kwargs
            See `ImportSession`.
        """

        super().__init__(state, config_overlay, **kwargs)

        if import_threshold is None:
            self.import_threshold = self.get_config_value(
                "match.strong_rec_thresh", float
            )
        else:
            self.import_threshold = import_threshold

    @property
    def stages(self):
        stages = super().stages
        stages.insert(before="user_query", stage=match_threshold(self))
        return stages

    def match_threshold(self, task: importer.ImportTask):
        """Check if the match quality is good enough to import.

        Returns true if candidates were found, and the match quality is better than
        threshlold.

        Note: What stops the pipeline is that we set task.choice to importer.action.SKIP,
        or raise an exception.

        Currently raising, as we do not have a dedicated progress for "not imported".

        FIXME: Instead of adding a whole new stage, with progress and a session function,
        we could simply extend the choose_match function. It's defined for the normal
        import session, and gets called early in user_query.
        (see #78)
        """
        try:
            task_state = self.state.get_task_state_for_task(task)
            distance = float(task_state.best_candidate_state.distance)  # type: ignore
        except (AttributeError, TypeError):
            distance = 2.0

        if len(task.candidates) == 0:
            raise NoCandidatesFoundException()

        if distance > self.import_threshold:
            log.debug(
                f"Best candidate was worse than threshold {distance=} {self.import_threshold=}"
            )
            d = (1 - distance) * 100
            t = (1 - self.import_threshold) * 100
            raise NotImportedException(f"Match below threshold ({d:.0f}% < {t:.0f}%)")
            # beets would handle this via the task action:
            task.set_choice(importer.action.SKIP)
        else:
            log.info(
                f"Best candidate was better than threshold, importing to library. {distance=} {self.import_threshold=}"
            )


class UndoSession(BaseSession):
    delete_files: bool

    def __init__(
        self,
        state: SessionState,
        config_overlay: dict | None = None,
        delete_files: bool = False,
        **kwargs,
    ):
        super().__init__(state, config_overlay, **kwargs)
        self.delete_files = delete_files

    async def run_async(self) -> SessionState:
        """Undo an import.

        A bit of a hack to reuse the BaseSession as we do
        not operate on tasks here but makes things easier in
        calling this in the invoker.

        Note: this Session should only be run in the (single-thread) import queue,
        because we want to limit beets-library and file interactions to be serial
        to avoid conflicts.
        """

        if self.state.progress != Progress.IMPORT_COMPLETED:
            log.error(
                f"Cannot undo import from state {self.state.progress}. "
                + "Only imports can be undone."
            )
            e = UserError(
                "Cannot undo if never imported! You need to import to undo first."
            )
            self.state.exc = to_serialized_exception(e)
            raise e

        for t_state in self.state.task_states:
            t_state.set_progress(Progress.DELETING)

        # Revert the movement of items that beets does during manipulate_files()
        # TODO: support Move operations (currently we only allow copy)

        # HACK: To allow an reimport after an undo, we need to use the old
        # paths of the items. This is a bit hacky, but We did not find
        # a better way to do this while maintaining the original beets logic.
        # -> the old_paths attribute of a beets_task is set during task.manipulate_files()
        # Unfortunately, here task.imported_items() does not work yet (.match not set)

        for t_state in self.state.task_states:
            chosen_candidate = t_state.chosen_candidate_state
            if chosen_candidate is None:
                raise ValueError("No chosen candidate found for task.")
            if t_state.task.old_paths is None:
                raise ValueError("No old paths found for task.")
            for idx, item in enumerate(chosen_candidate.match.mapping.keys()):  # type: ignore
                # yes, keys are the items and need to be updated!
                # mapping maps objects to objects.
                item.path = t_state.task.old_paths[idx]

        # Delete files
        excs: list[Exception] = []
        pths: list[Path] = []
        for t_state in self.state.task_states:
            try:
                delete_from_beets(t_state.id, self.delete_files, self.lib)
            except Exception as e:
                items = self.lib.items(f"gui_import_id:{t_state.id}")

                excs.append(e)
                pths.extend([Path(item.path.decode("utf-8")) for item in items])

        if len(excs) > 0:
            for exc in excs:
                log.exception(exc)

            # FIXME: Multi/array exceptions need handling
            self.state.exc = to_serialized_exception(excs[0])
            raise IntegrityException(
                "Could not delete all items. Some items might be left in the library. "
                + f"Problematic files were: {pths}"
            )

        # Update our state and progress
        for t_state in self.state.task_states:
            t_state.set_progress(Progress.DELETION_COMPLETED)

        # Send cli_exit event to have compatibility with beets plugin that
        # execute after the import is completed.
        plugins.send("cli_exit", lib=self.lib)

        return self.state

    @property
    def stages(self):
        # This tweaked session skips the pipeline
        return StageOrder()


## Edge cases
# 1. Session doesn't exist anymore -> delete
# 2. Session exists but multiple tasks -> undo (session)
# 3. Session exists but file do not anymore in import folder -> undo, warnings

# Flow:
# - remove from beets db
# - revert our session (if possible)


def delete_from_beets(task_id: str, delete_files: bool, lib: BeetsLibrary):
    """Low-level, delete the items from the beets library."""

    # We set a gui_import_id in the beets database this is equal to the session id
    # see _apply_choice in stages.py

    items = lib.items(f"gui_import_id:{task_id}")

    if len(items) == 0:
        raise ValueError("No items found that match this import session id.")

    with lib.transaction():
        for item in items:
            item.remove(delete_files)
