from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from typing import TypedDict

__all__ = [
    "FolderStatus",
    "Progress",
    "ProgressState",
    "SerializedProgressState",
]


@total_ordering
class Progress(Enum):
    """The progress of tasks in chronological order.

    The order roughly matches the stages you might expect.

    Allows to resume a import at any time using our state dataclasses. We might
    also want to add the plugin stages or refine this.
    """

    NOT_STARTED = 0

    # PreviewSession
    READING_FILES = 10
    GROUPING_ALBUMS = 11
    LOOKING_UP_CANDIDATES = 12
    IDENTIFYING_DUPLICATES = 13

    PREVIEW_COMPLETED = 20  # dummy, only for comparison and report, has no actual stage
    DELETION_COMPLETED = 21  # dummy. after a successful deletion, we can restart import

    # ImportSession
    OFFERING_MATCHES = 30
    MATCH_THRESHOLD = 31
    WAITING_FOR_USER_SELECTION = 32
    EARLY_IMPORTING = 33
    IMPORTING = 34
    MANIPULATING_FILES = 35

    IMPORT_COMPLETED = 40  # also a dummy

    # UndoSession
    DELETING = 50

    def __lt__(self, other: Progress | ProgressState) -> bool:
        if isinstance(other, ProgressState):
            other = other.progress
        return self.value < other.value

    def __sub__(self, other: int) -> Progress:
        if not isinstance(other, int):
            raise TypeError("Unsupported type for addition")

        other = max(min(self.value - other, 50), 0)
        return Progress(other)

    def __add__(self, other: int) -> Progress:
        return self.__sub__(-1 * other)


class SerializedProgressState(TypedDict):
    # ugly to repeat, but no way to read the type hint from enum.
    progress: Progress
    message: str | None
    plugin_name: str | None


@total_ordering
@dataclass(slots=True)
class ProgressState:
    """Simple dataclass to hold a status message and a status code."""

    progress: Progress = Progress.NOT_STARTED

    # Optional message to display to the user
    message: str | None = None

    # Plugin specific
    plugin_name: str | None = None

    def serialize(self) -> SerializedProgressState:
        return SerializedProgressState(
            progress=self.progress,
            message=self.message,
            plugin_name=self.plugin_name,
        )

    def __lt__(self, other: ProgressState | Progress) -> bool:
        if isinstance(other, Progress):
            other = ProgressState(other)
        return self.progress < other.progress

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Progress):
            return self.progress == other
        if not isinstance(other, ProgressState):
            return False
        return self.progress == other.progress


class FolderStatus(int, Enum):
    """The status of a folder.

    Order does not matter, but we need to be able to check equality
    """

    UNKNOWN = -2
    FAILED = -1
    NOT_STARTED = 0
    PENDING = 1
    PREVIEWING = 2
    PREVIEWED = 3
    IMPORTING = 4
    IMPORTED = 5
    DELETING = 6
    DELETED = 7

    def __str__(self) -> str:
        return self.name.lower()
