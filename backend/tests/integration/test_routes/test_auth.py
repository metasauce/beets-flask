"""Tests for the auth endpoints."""

from typing import ClassVar

import pytest

from beets_flask.extensions.auth import AuthExtension, PkceData
from beets_flask.server.routes import auth as auth_routes

PKCE = PkceData(code_verifier="verifier", state="state")


class FakeAuth(AuthExtension):
    """Deterministic stand-in for a real auth provider."""

    name: ClassVar[str] = "fake"
    completed_with: tuple[PkceData, str] | None = None

    @classmethod
    def is_enabled(cls) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return False

    def start_authentication(self) -> tuple[PkceData, str]:
        return PKCE, "https://example.com/authorize"

    def complete_authentication(self, pkce: PkceData, redirect_url: str) -> None:
        self.completed_with = (pkce, redirect_url)


@pytest.fixture
def fake_auth(monkeypatch) -> FakeAuth:
    auth = FakeAuth()
    monkeypatch.setattr(auth_routes, "AUTH_EXTENSIONS", [auth])
    return auth


class TestAuthProviders:
    async def test_lists_provider_status(self, client, fake_auth):
        response = await client.get("/api_v1/auth/providers")

        assert response.status_code == 200
        data = await response.get_json()
        assert data == [{"name": "fake", "authenticated": False}]

    async def test_skips_disabled_providers(self, client, monkeypatch):
        class DisabledFake(FakeAuth):
            @classmethod
            def is_enabled(cls) -> bool:
                return False

        monkeypatch.setattr(auth_routes, "AUTH_EXTENSIONS", [DisabledFake()])

        response = await client.get("/api_v1/auth/providers")

        assert response.status_code == 200
        data = await response.get_json()
        assert data == []


class TestAuthUrl:
    async def test_returns_url_and_flow_id(self, client, fake_auth, fake_redis):
        response = await client.get("/api_v1/auth/fake/url")

        assert response.status_code == 200
        data = await response.get_json()
        assert data["url"] == "https://example.com/authorize"
        assert data["flow_id"]

        # The sensitive flow state is stored server-side, not returned.
        assert "code_verifier" not in data
        assert "state" not in data

    async def test_unknown_provider_returns_400(self, client):
        response = await client.get("/api_v1/auth/does-not-exist/url")

        assert response.status_code == 400


class TestAuthComplete:
    async def test_completes_authentication(self, client, fake_auth, fake_redis):
        redirect_url = "https://example.com/callback?code=abc123"

        start = await client.get("/api_v1/auth/fake/url")
        flow = await start.get_json()

        response = await client.post(
            "/api_v1/auth/fake/complete",
            json={"redirect_url": redirect_url, "flow_id": flow["flow_id"]},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data == {"authenticated": True}
        assert fake_auth.completed_with == (PKCE, redirect_url)

    async def test_missing_parameters_returns_400(self, client, fake_auth):
        response = await client.post(
            "/api_v1/auth/fake/complete", json={"redirect_url": "x"}
        )
        assert response.status_code == 400

        response = await client.post(
            "/api_v1/auth/fake/complete", json={"flow_id": "x"}
        )
        assert response.status_code == 400

    async def test_unknown_flow_returns_400(self, client, fake_auth, fake_redis):
        response = await client.post(
            "/api_v1/auth/fake/complete",
            json={"redirect_url": "x", "flow_id": "does-not-exist"},
        )

        assert response.status_code == 400

    async def test_unknown_provider_returns_400(self, client):
        response = await client.post(
            "/api_v1/auth/does-not-exist/complete",
            json={"redirect_url": "x", "flow_id": "x"},
        )

        assert response.status_code == 400
