"""We maintain the configuration schema for beets-flask here.

This also includes schemas for beets sections that we need to access in
beets-flask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------- #
#                                     Beets                                    #
# ---------------------------------------------------------------------------- #


@dataclass
class BeetsSchema:
    gui: BeetsFlaskSchema = field(default_factory=lambda: BeetsFlaskSchema())

    # Besides the beets-flask specific config, we want to ensure type safety
    # for those fields of the native beets config that we use ourselves.
    directory: str = field(default="/music/imported")
    ignore: list[str] = field(
        default_factory=lambda: [".*", "*~", "System Volume Information", "lost+found"]
    )
    plugins: list[str] = field(default_factory=lambda: ["musicbrainz"])

    # `import` is a reserved keyword in Python. Eyconf's workaround is an alias.
    import_: ImportSection = field(
        default_factory=lambda: ImportSection(),
        metadata={"alias": "import"},  # the alias is used in yaml and dict-style access
    )
    match: MatchSectionSchema = field(default_factory=lambda: MatchSectionSchema())

    # known plugins
    aisauce: PluginAiSauceSchema = field(default_factory=lambda: PluginAiSauceSchema())
    # Note: we currently set the defaults from the schema in commit_to_beets.
    # This prevents us from using None as default value in beets root-level entries.
    # For instance `aisauce: PluginAiSauceSchema | None = None` wont work, we need
    # to sepcify a default schema - to know the defaults for every plugin we add.


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


# ---------------------------------- Library --------------------------------- #


@dataclass
class LibrarySectionSchema:
    readonly: bool = False
    artist_separators: list[str] = field(default_factory=lambda: [",", ";", "&"])


# --------------------------------- Terminal --------------------------------- #


@dataclass
class TerminalSectionSchema:
    enabled: bool = True
    start_path: str = "/repo"


# ----------------------------------- Inbox ---------------------------------- #


@dataclass
class InboxSectionSchema:
    ignore: list[str] | Literal["_use_beets_ignore"] = "_use_beets_ignore"
    # File patterns to ignore when scanning the inbox folders.
    # Useful to exclude temporary files from being shown in the inbox.
    # To show all files (independent of which files beets will copy) set to []
    debounce_before_autotag: int = 30
    temp_dir: str = field(default="/tmp/beets-flask/upload")
    folders: dict[str, InboxFolderSchema] = field(
        default_factory=lambda: {
            "placeholder": InboxFolderSchema(
                name="Please check your config!",
                path="/music/beets_flask_config_example/inbox_placeholder",
                autotag="off",
            )
        }
    )


@dataclass
class InboxFolderSchema:
    path: str
    name: str = "_use_heading"  # names should be unique
    auto_threshold: float | None = None
    autotag: Literal["auto", "preview", "bootleg", "off"] = "off"
    overrides: InboxSpecificOverridesSchema = field(
        default_factory=lambda: InboxSpecificOverridesSchema()
    )


@dataclass
class InboxSpecificOverridesSchema:
    plugins: list[str] | Literal["_use_all"] = "_use_all"
    aisauce: PluginAiSauceSchema = field(default_factory=lambda: PluginAiSauceSchema())


# ---------------------------------- Plugins --------------------------------- #


@dataclass
class PluginAiSauceSchema:
    mode: Literal["metadata_source", "metadata_cleanup"] = "metadata_cleanup"
    providers: list[PluginAiSauceProviderSchema] = field(default_factory=lambda: [])
    sources: list[PluginAiSauceSourceSchema] = field(default_factory=lambda: [])


@dataclass
class PluginAiSauceProviderSchema:
    id: str
    model: str
    api_key: str
    api_base_url: str

@dataclass
class PluginAiSauceSourceSchema:
    provider_id: str
    user_prompt: str | None
    system_prompt: str | None
