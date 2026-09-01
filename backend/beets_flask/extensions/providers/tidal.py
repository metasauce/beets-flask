from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, ClassVar

from beets import plugins as beets_plugins
from beets.exceptions import UserError

from beets_flask.logger import log

from .. import AuthExtension, PkceData

if TYPE_CHECKING:
    from beetsplug.tidal import TidalPlugin


class TidalAuth(AuthExtension):
    """Authenticate with Tidal.

    Implements the same auth flow as in beets' Tidal plugin, using the
    `requests-oauthlib` session to generate the auth URL and exchange the code for a
    token.
    """

    name: ClassVar[str] = "tidal"

    @classmethod
    def is_enabled(cls) -> bool:
        return cls.tidal_plugin() is not None

    @classmethod
    @cache
    def tidal_plugin(cls) -> TidalPlugin | None:
        """Return beets' loaded Tidal plugin, if enabled."""
        try:
            from beetsplug.tidal import TidalPlugin as _TidalPlugin
        except ImportError as err:
            log.debug("Tidal plugin is unavailable: %s", err)
            return None

        return next(
            (
                plugin
                for plugin in beets_plugins.find_plugins()
                if isinstance(plugin, _TidalPlugin)
            ),
            None,
        )

    def is_authenticated(self) -> bool:
        """Check if the user is authenticated with Tidal."""
        plugin = self.tidal_plugin()
        if plugin is None:
            return False

        # Raises UserError if not authenticated
        try:
            plugin.require_authentication()
        except UserError:
            return False

        return True

    def start_authentication(self) -> tuple[PkceData, str]:
        """Start the PKCE flow: build the login URL and return the flow state.

        The PKCE verifier and CSRF state live on the OAuth session object,
        which is process-local, so they are returned here as sensitive
        :class:`PkceData`. The caller is responsible for persisting them
        server-side until the flow is completed.
        """
        plugin = self.tidal_plugin()
        if plugin is None:
            raise RuntimeError("The Tidal plugin is not enabled.")

        session = plugin.api.session
        auth_url, state = session.authorization_url("https://login.tidal.com/authorize")
        pkce = PkceData(code_verifier=session._code_verifier, state=state)
        return pkce, auth_url

    def complete_authentication(self, pkce: PkceData, redirect_url: str) -> None:
        """Exchange the auth code from ``redirect_url`` for a token and save it.

        The PKCE state from ``pkce`` is restored on the OAuth session before
        the exchange, so it can run on any worker.
        """

        plugin = self.tidal_plugin()
        if plugin is None:
            raise RuntimeError("The Tidal plugin is not enabled.")

        session = plugin.api.session
        session._state = pkce.state
        session._code_verifier = pkce.code_verifier
        session.fetch_token(
            "https://auth.tidal.com/v1/oauth2/token",
            authorization_response=redirect_url,
            include_client_id=True,
        )
        session.save_token(session.token)
