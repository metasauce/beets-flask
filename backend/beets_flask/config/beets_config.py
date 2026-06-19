from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Literal, Self, cast

import beets
import yaml
from beets.plugins import _instances as plugin_instances
from beets.plugins import get_plugin_names, load_plugins
from eyconf import ConfigExtra
from eyconf.asdict import asdict_with_aliases
from eyconf.validation import ConfigurationError, MultiConfigurationError
from yaml import YAMLError
from yaml.scanner import ScannerError

from beets_flask.logger import log
from beets_flask.utility import deprecation_warning

from .schema import BeetsSchema

_BEETS_EXAMPLE_PATH = Path(os.path.dirname(__file__)) / "config_b_example.yaml"
_BF_EXAMPLE_PATH = Path(os.path.dirname(__file__)) / "config_bf_example.yaml"


class BeetsFlaskConfig(ConfigExtra[BeetsSchema]):
    """Base config class with extra fields support."""

    def __init__(self):
        """Initialize the config object with the default values."""
        super().__init__(schema=BeetsSchema, data=BeetsSchema())
        BeetsFlaskConfig.write_examples_as_user_defaults()
        self.reload()
        self.commit_to_beets()

    @classmethod
    def get_beets_flask_config_path(cls) -> Path:
        """Get the path to the beets-flask config file."""
        bf_folder = os.getenv(
            "BEETSFLASKDIR", os.path.expanduser("~/.config/beets-flask")
        )
        return Path(bf_folder) / "config.yaml"

    @classmethod
    def get_beets_config_path(cls) -> Path:
        """Get the path to the beets config file."""
        beets_folder = os.getenv("BEETSDIR", os.path.expanduser("~/.config/beets"))
        return Path(beets_folder) / "config.yaml"

    @staticmethod
    def load_yaml(path: str | Path) -> dict[str, Any]:
        """Try to load a yaml and reraise errors as configuration errors."""
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except (ScannerError, YAMLError) as e:
            raise ConfigurationError(message=str(e))

    def reload(self, extra_yaml_path: str | Path | None = None) -> Self:
        """Reload the config.

        This loads the user config from yaml files after resetting to defaults.

        The `extra_yaml_path` argument is mainly for testing purposes, to add a last
        yaml layer with high priority.

        Any error messages (YAML parsing, validation) are stored for upstream handling
        """
        log.debug("Resetting/Reloading config")
        super().reset()

        # Config sources:
        # 1. beets defaults
        # We do not load them into _our_ config.
        # They are still available in the beets_config property.
        # But: we want to encourage user to add fields that are accessed
        # from _our_ config into the schema.
        # Thus only porting requirement: copy the relevant beets default into the schema
        # 2. beets-flask user config
        # 3. extra config

        sources: list[Path] = [
            self.get_beets_config_path(),
            self.get_beets_flask_config_path(),
        ]
        if extra_yaml_path is not None:
            sources.append(Path(extra_yaml_path))

        for path in sources:
            if path.exists():
                # EYConfs update method also validates against the schema
                self.update(self.load_yaml(path))

        return self

    def commit_to_beets(self) -> None:
        """
        Insert the current state of self into the native beets config.

        Resets the beets config before inserting the new values.

        Only call manually when needed, i.e. after modifying the bf config.
        This is somewhat slow.
        """

        beets.config.clear()
        beets.config.read()

        # Put our defaults that come from schema at lowest priority
        beets.config.add(asdict_with_aliases(BeetsSchema()))

        # Inserts user config into confuse
        beets.config.set(self.to_dict(extra_fields=True))

        # Hack: We have to manually load the plugins as this
        # is normally done by beets. Clear the list to force
        # actual reload.
        plugin_instances.clear()
        load_plugins()
        log.debug(f"Loading plugins: {get_plugin_names()}")

        # Beets config "Singleton" is not a real singleton, there might be copies
        # in different submodules - we need to update all of them.
        # TODO: Can we remove this? PS 2025-11-02: I dont think so, because we still do
        # not know if plugins make a copy of the beets config when they are initialized.
        for module_name, mod in list(sys.modules.items()):
            if mod is None:
                continue

            if not (
                module_name.startswith("beets")  # includes beets and beetsplug
            ):
                continue

            for attr_name in dir(mod):
                try:
                    if getattr(mod, attr_name) is beets.config:
                        setattr(mod, attr_name, beets.config)
                        log.debug(f"Updated config in {module_name}.{attr_name}")
                except Exception as e:
                    log.debug(f"Could not check {module_name}.{attr_name}", exc_info=e)
                    continue

    def validate(self):
        """Validate and sanitize the config data.

        We apply some light transformations to make things more convenient.
        """
        super().validate()

        # make sure to remove trailing slashes from user configured inbox paths
        # we could also fix this in the frontend, but this was easier.
        missing_folder_errors = []
        for key in self.data.gui.inbox.folders.keys():
            folder = self.data.gui.inbox.folders[key]
            if folder.path.endswith("/"):
                folder.path = folder.path.rstrip("/")
                log.warning(f"Removed trailing slash from inbox path: {folder.path}")

            # Allow more convenient yaml, so users can use the heading instead of name
            if folder.name == "_use_heading":
                folder.name = key

            # Since we changed the autotag type from False to "off" with v1.2.0,
            # Let's fix old configs and warn
            if folder.autotag is False:
                folder.autotag = "off"
                deprecation_warning(
                    "The inbox autotag setting 'False'",
                    alt_text="Update your configuration and use 'off' instead.",
                )

            if (
                not Path(folder.path).exists()
                and not str(folder.path).startswith(
                    "/music/beets_flask_config_example/"
                )
                # prevent validation errors on our user examples and default value
            ):
                missing_folder_errors.append(
                    ConfigurationError(
                        f"Inbox folder path does not exist: {folder.path}",
                        section="gui.inbox.folders",
                    )
                )

        if len(missing_folder_errors) > 1:
            raise MultiConfigurationError(missing_folder_errors)
        elif len(missing_folder_errors) == 1:
            raise missing_folder_errors[0]

    @classmethod
    def write_examples_as_user_defaults(cls):
        """Write example config files if they do not exist yet.

        Note that we also place an opinionated example for beets,
        because it does not do that itself.
        """
        # Load config from default location (set via env var)
        # if it is set otherwise use the default location
        bf_config_path = cls.get_beets_flask_config_path()

        # Check if the user config exists
        # if not, copy the example config to the user config location
        did_copy = False
        if not os.path.exists(bf_config_path):
            did_copy = True
            os.makedirs(os.path.dirname(bf_config_path), exist_ok=True)
            # Copy the default config to the user config location
            log.info(f"Beets-flask config not found at {bf_config_path}")
            log.info(f"Copying default config to {bf_config_path}")
            shutil.copy2(_BF_EXAMPLE_PATH, bf_config_path)

        # Same check for beets config and copy our default
        # if it does not exist
        beets_config_path = cls.get_beets_config_path()
        if not os.path.exists(beets_config_path):
            did_copy = True
            os.makedirs(os.path.dirname(beets_config_path), exist_ok=True)
            log.info(f"Beets config not found at {beets_config_path}")
            log.info(f"Copying default config to {beets_config_path}")
            shutil.copy2(_BEETS_EXAMPLE_PATH, beets_config_path)

        # To pass validation checks, we also need the folders shown in the config demo
        # to be present. Otherwise the frontend wont be usable on first start.
        if did_copy:
            log.info(f"Creating demo inboxes at /music/beets_flask_config_example/")
            for dir in [
                "/music/beets_flask_config_example/imported",
                "/music/beets_flask_config_example/inbox_off",
                "/music/beets_flask_config_example/inbox_auto",
                "/music/beets_flask_config_example/inbox_preview",
            ]:
                try:
                    os.makedirs(dir, exist_ok=True)
                except OSError:
                    log.info(
                        "Could not create beets_flask_config_example directories, "
                        + "likely because this was not run inside the docker container."
                    )

    # ------------------------------ Utility getters ----------------------------- #

    @property
    def beets_config(self) -> beets.IncludeLazyConfig:
        """Convenience property to get the native beets config."""
        # Aavoid calling refresh_confuse here. We often access the beets config,
        # and updating it every time makes things very slow.
        return beets.config

    @property
    def beets_version(self) -> str:
        """Get the current beets version."""
        return beets.__version__

    @property
    def beets_metadata_sources(self) -> list[str]:
        """Get the list of enabled metadata source plugins."""
        from beets.metadata_plugins import find_metadata_source_plugins

        return [p.data_source for p in find_metadata_source_plugins()]

    @property
    def ignore_globs(self) -> list[str]:
        """
        Get the list of ignore globs from the config.

        If user does not set this in their beets flask config, we use whats in beets.
        (We do this via a placeholder string "_use_beets_ignore")
        If the user sets an empty list [], that means no files are ignored.
        """
        gui_globs: list[str] | Literal["_use_beets_ignore"] = self.data.gui.inbox.ignore
        if gui_globs is None or gui_globs == "_use_beets_ignore":
            gui_globs = self.data.ignore
        return cast(list[str], gui_globs)


config: BeetsFlaskConfig | None = None


def get_config(force_reload=False, commit_to_beets=False) -> BeetsFlaskConfig:
    """Get the config object.

    This is useful if you want to access the config from another module.

    The result of this function is still the global object that you can mutate!

    Parameters
    ----------
    force_reload : bool
        Force a refresh of the config object, including the global beets config.

    """
    global config

    if config is None:
        config = BeetsFlaskConfig()
        return config
    if force_reload:
        config.reload()
    if commit_to_beets:
        config.commit_to_beets()
    return config
