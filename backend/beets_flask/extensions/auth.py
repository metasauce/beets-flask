"""Auth extension: Provides generic authentication support for plugins that need it.

Some plugins needs authentication to access their API or work at all, e.g. tidal needs
you to run `beet tidal --auth`
"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class PkceData:
    """Sensitive PKCE flow state (RFC 7636).

    The ``code_verifier`` is required to redeem the authorization code, and
    ``state`` binds the redirect URL to the flow (CSRF). Together they make
    the flow stateless across processes: they must be persisted server-side
    between the two steps and must never reach the client.
    """

    code_verifier: str
    state: str


class AuthExtension:
    """Interface for an authentication extension.

    Provides a way to check for authentication and to perform authentication if needed.

    Only the PKCE flow (see RFC 7636) is supported right now: the user authenticates in
    their browser, and the resulting authorization code is exchanged for a token.
    Extensions implement this as two steps:

    1. :meth:`start_authentication` returns the sensitive :class:`PkceData`
       plus the URL the user must visit.
    2. After the user logs in, the service redirects back to a URL
       containing an authorization code. The caller passes that redirect
       URL (together with the flow state) to
       :meth:`complete_authentication`, which exchanges the code for a
       token and persists it.

    The extension itself does not persist any state; the caller is
    responsible for keeping the (sensitive) flow state server-side between
    the two steps, e.g. in the app's storage backend.

    Other flows (e.g. client credentials) may be added later if a plugin
    requires them.
    """

    name: ClassVar[str]

    @classmethod
    @abstractmethod
    def is_enabled(cls) -> bool:
        """Return whether the provider is available (e.g. its plugin is enabled)."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Return whether the user is authenticated."""

    @abstractmethod
    def start_authentication(self) -> tuple[PkceData, str]:
        """Start the PKCE flow.

        Returns the sensitive :class:`PkceData` and the URL the user must
        visit.
        """

    @abstractmethod
    def complete_authentication(self, pkce: PkceData, redirect_url: str) -> None:
        """Complete the flow using the state from ``start_authentication``.

        The ``redirect_url`` contains the authorization code, which is
        exchanged for a token.
        """
