"""We maintain the configuration schema for beets-flask here.

This also includes schemas for beets sections that we need to access in
beets-flask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class BeetsSchema:
    gui: BeetsFlaskSchema = field(default_factory=lambda: BeetsFlaskSchema())

    # Besides the beets-flask specific config, we want to ensure type safety
    # for those fields of the native beets config that we use ourself.
    directory: str = field(default="/music/imported")
    ignore: list[str] = field(default_factory=lambda: [])
    plugins: list[str] = field(default_factory=lambda: [])

    # `import` is a reserved keyword in Python. Eyconf's workaround is an alias.
    import_: ImportSection = field(
        default_factory=lambda: ImportSection(),
        metadata={"alias": "import"},  # the alias is used in yaml and dict-style access
    )
    match: MatchSectionSchema = field(default_factory=lambda: MatchSectionSchema())


# ---------------------------------------------------------------------------- #
#                                     Beets                                    #
# ---------------------------------------------------------------------------- #


@dataclass
class ImportSection:
    duplicate_action: Literal["ask", "skip", "merge", "keep", "remove"] = "remove"
    move: Literal[False] = False  # beets-flask does not support the move option
    copy: Literal[True] = True  # let's shape expectations via config
    duplicate_keys: ImportDuplicateKeys = field(
        default_factory=lambda: ImportDuplicateKeys()
    )


@dataclass
class ImportDuplicateKeys:
    # legacy compatibility, beets uses a space-delimited str sequence
    # we could make a PR in beets to change the defaults
    # in confuse, when using .str_seq both syntaxes in yaml work
    # but `.get` will give different results
    album: str | list[str] = field(default_factory=lambda: ["albumartist", "album"])
    item: str | list[str] = field(default_factory=lambda: ["artist", "title"])


@dataclass
class MatchSectionSchema:
    strong_rec_thresh: float = field(default=0.04)
    medium_rec_thresh: float = field(default=0.10)


# ---------------------------------------------------------------------------- #
#                                  Beets Flask                                 #
# ---------------------------------------------------------------------------- #


@dataclass
class BeetsFlaskSchema:
    """Beets-flask specific configuration schema."""

    inbox: InboxSectionSchema = field(default_factory=lambda: InboxSectionSchema())
    library: LibrarySectionSchema = field(
        default_factory=lambda: LibrarySectionSchema()
    )
    terminal: TerminalSectionSchema = field(
        default_factory=lambda: TerminalSectionSchema()
    )
    num_preview_workers: int = field(default=4)


# ----------------------------------- Inbox ---------------------------------- #


@dataclass
class InboxSectionSchema:
    ignore: list[str] | Literal["_use_beets_ignore"] = "_use_beets_ignore"
    # File patterns to ignore when scanning the inbox folders.
    # Useful to exclude temporary files from being shown in the inbox.
    # To show all files (independent of which files beets will copy) set to []
    debounce_before_autotag: int = 30
    folders: dict[str, InboxFolderSchema] = field(
        default_factory=lambda: {
            "placeholder": InboxFolderSchema(
                name="Please check your config!",
                path="/music/inbox",
                autotag="off",
            )
        }
    )


@dataclass
class InboxFolderSchema:
    path: str
    name: str = "_use_heading"
    auto_threshold: float | None = None
    autotag: Literal["auto", "preview", "bootleg", "off"] = "off"


# ---------------------------------- Library --------------------------------- #


@dataclass
class LibrarySectionSchema:
    readonly: bool = False
    artist_separators: list[str] = field(default_factory=lambda: [",", ";", "&"])


# --------------------------------- Terminal --------------------------------- #


@dataclass
class TerminalSectionSchema:
    start_path: str = "/repo"
