"""Unit tests for the Tidal auth provider."""

from types import SimpleNamespace
from typing import Any

import pytest
from beets.exceptions import UserError

from beets_flask.extensions.auth import PkceData
from beets_flask.extensions.providers.tidal import TidalAuth

AUTH_URL = "https://login.tidal.com/authorize"
TOKEN_URL = "https://auth.tidal.com/v1/oauth2/token"


class FakeSession:
    """Minimal stand-in for the beets tidal OAuth session."""

    def __init__(self, code_verifier: str = "verifier", state: str = "state") -> None:
        self._code_verifier = code_verifier
        self._state = state
        self.token: dict[str, str] | None = None
        self.saved_token: dict[str, str] | None = None
        self.fetch_token_kwargs: dict[str, Any] | None = None

    def authorization_url(self, url: str) -> tuple[str, str]:
        return f"{url}?code_challenge=xyz", self._state

    def fetch_token(self, token_url: str, **kwargs) -> None:
        self.fetch_token_kwargs = {"token_url": token_url, **kwargs}
        self.token = {"access_token": "token", "refresh_token": "refresh"}

    def save_token(self, token: dict[str, str]) -> None:
        self.saved_token = token


class FakePlugin:
    """Minimal stand-in for beets' ``TidalPlugin``."""

    def __init__(self, session: FakeSession, authenticated: bool = True) -> None:
        self.api = SimpleNamespace(session=session)
        self.authenticated = authenticated

    def require_authentication(self) -> None:
        if not self.authenticated:
            raise UserError("Please login to TIDAL")


@pytest.fixture
def fake_plugin(monkeypatch) -> FakePlugin:
    """Replace ``TidalAuth.tidal_plugin`` with a fake plugin instance."""
    plugin = FakePlugin(FakeSession())
    monkeypatch.setattr(TidalAuth, "tidal_plugin", classmethod(lambda cls: plugin))
    return plugin


@pytest.fixture
def no_plugin(monkeypatch):
    """Make the tidal plugin unavailable."""
    monkeypatch.setattr(TidalAuth, "tidal_plugin", classmethod(lambda cls: None))


class TestTidalAuth:
    def test_start_authentication_returns_pkce_and_url(self, fake_plugin):
        pkce, url = TidalAuth().start_authentication()

        assert url == f"{AUTH_URL}?code_challenge=xyz"
        assert pkce == PkceData(code_verifier="verifier", state="state")

    def test_start_authentication_raises_without_plugin(self, no_plugin):
        with pytest.raises(RuntimeError, match="not enabled"):
            TidalAuth().start_authentication()

    def test_complete_authentication_restores_state_and_saves_token(self, fake_plugin):
        pkce = PkceData(code_verifier="verifier2", state="state2")
        redirect_url = "https://example.com/callback?code=abc123"

        TidalAuth().complete_authentication(pkce, redirect_url)

        session = fake_plugin.api.session
        assert session._code_verifier == "verifier2"
        assert session._state == "state2"
        assert session.fetch_token_kwargs == {
            "token_url": TOKEN_URL,
            "authorization_response": redirect_url,
            "include_client_id": True,
        }
        assert session.saved_token == session.token

    def test_complete_authentication_raises_without_plugin(self, no_plugin):
        with pytest.raises(RuntimeError, match="not enabled"):
            TidalAuth().complete_authentication(
                PkceData(code_verifier="v", state="s"),
                "https://example.com/callback?code=abc",
            )

    def test_is_authenticated_true_when_authenticated(self, fake_plugin):
        assert TidalAuth().is_authenticated() is True

    def test_is_authenticated_false_when_not_authenticated(self, monkeypatch):
        plugin = FakePlugin(FakeSession(), authenticated=False)
        monkeypatch.setattr(TidalAuth, "tidal_plugin", classmethod(lambda cls: plugin))

        assert TidalAuth().is_authenticated() is False

    def test_is_authenticated_false_without_plugin(self, no_plugin):
        assert TidalAuth().is_authenticated() is False
