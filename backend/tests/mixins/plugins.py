from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, ClassVar
from unittest import mock

import pytest
from beets.plugins import send

if TYPE_CHECKING:
    from beets.events import EventType


class PluginEventsMixin(ABC):
    """
    Allows to test events sent by plugins.
    This mixin captures events sent by plugins during tests.

    Usage:
    ```
    class TestMyPlugin(PluginEventsMixin):
        def test_event(self):
            self.send_event("my_event", data="test")
            assert "my_event" in self.events
    ```

    """

    events: ClassVar[list[str]] = []

    def send_event(self, event: EventType, **kwargs):
        self.events.append(event)
        return send(event, **kwargs)

    @pytest.fixture(autouse=True, scope="function")
    def mock_events(self):
        """Mock the emit_status decorator"""

        with mock.patch(
            "beets.plugins.send",
            self.send_event,
        ):
            yield

        # Clear the shared capture list so events do not leak into the next test.
        self.events.clear()
