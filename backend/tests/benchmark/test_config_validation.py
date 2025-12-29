"""Verify that our rewrite of config using eyconf is as fast as confuse"""

import beets
from beets.plugins import _instances as plugin_instances
from beets.plugins import load_plugins

from beets_flask.config import get_config


def _reset_beets():
    beets.config.clear()
    beets.config.read()
    loaded_data = beets.config.flatten()
    plugin_instances.clear()
    load_plugins()


def _reset_beets_flask():
    config = get_config()
    config.reload()
    config.commit_to_beets()


def test_beets_config(benchmark):
    benchmark(_reset_beets)


def test_beets_flask_config(benchmark):
    config = get_config()
    benchmark(_reset_beets_flask)
