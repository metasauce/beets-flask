import logging
import os

from beets_flask.logger import log


def test_log():
    """Test that logger is correctly set up for testing."""

    assert "PYTEST_CURRENT_TEST" in os.environ

    # Pytest may inject capture handlers; just ensure no file handler is attached.
    assert not any(isinstance(handler, logging.FileHandler) for handler in log.handlers)
    assert log.level == logging.DEBUG
    assert log.name == "beets-flask"


def test_config():
    """Test that config is correctly set up for testing."""
    import tempfile

    dir_bf = os.environ.get("BEETSFLASKDIR")
    assert dir_bf is not None
    assert str(tempfile.tempdir) in dir_bf

    dir_b = os.environ.get("BEETSDIR")
    assert dir_b is not None
    assert str(tempfile.tempdir) in dir_b
