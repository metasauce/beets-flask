import asyncio
import os
from pathlib import Path

import pytest

from beets_flask.config import get_config
from beets_flask.config.schema import InboxFolderSchema
from beets_flask.watchdog.inbox import InboxHandler, register_inboxes


@pytest.fixture(scope="function")
def preview_autotag(tmpdir_factory):
    """
    Setup for the watchdog tests.
    This fixture will run before and after all tests in this module.
    """
    config = get_config()
    config.data.gui.inbox.folders = {
        "inbox1": InboxFolderSchema(
            name="inbox1",
            path=tmpdir_factory.mktemp("inbox").strpath,
            autotag="preview",
        ),
    }
    yield
    config.reload()


from unittest import mock


@pytest.fixture(scope="function")
def mp_en():
    """
    A fixture to mock the `enqueue` function in the `invoker` module.
    This allows us to test the behavior of the inbox handler without
    actually enqueuing tasks.
    """

    calls = []

    with mock.patch(
        "beets_flask.watchdog.inbox.auto_tag",
        lambda *args, **kwargs: calls.append((*args, *kwargs)),
    ):
        yield calls


async def test_watchdog(preview_autotag, mp_en):
    """Start watching the inbox folder"""

    config = get_config()
    inbox_path = Path(str(config.data.gui.inbox.folders["inbox1"].path))
    inbox_autotag = config.data.gui.inbox.folders["inbox1"].autotag

    assert inbox_path.is_dir(), "Inbox path should be a directory"
    assert inbox_autotag == "preview", "Inbox autotag should be set to 'preview'"

    watchdog = register_inboxes(0.1, 0.5)  # timeout=1s, debounce=30s
    assert watchdog is not None, "Watchdog should be initialized"
    assert watchdog._observer.is_alive(), "Watchdog should be running"

    # Touch file in inbox
    os.makedirs(inbox_path / "album", exist_ok=True)
    (inbox_path / "album" / "test.mp3").touch()

    h = watchdog._handler
    assert isinstance(h, InboxHandler), (
        "Handler should be an instance of AIOEventHandler"
    )
    await asyncio.sleep(0.12)  # Allow time for the observer to start task
    task = list(h.debounce.values())[0]
    assert task is not None, "Debounce should have a task after touching file"
    # Check task is running
    assert not task.done(), "Task should not be done immediately after touching file"

    # Touch again and check that task is cancelled
    (inbox_path / "album" / "test.mp3").touch()
    await asyncio.sleep(0.12)  # Allow debounce time
    assert task.cancelled(), "Task should be cancelled by new incoming ones"

    # Check that the task is not running anymore
    task_2 = list(h.debounce.values())[0]
    await asyncio.sleep(1)
    assert task_2.done(), "Task should be done after debounce time"
    assert mp_en[0][0] == (inbox_path / "album").resolve()
